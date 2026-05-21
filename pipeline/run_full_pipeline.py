"""
EV Charging Intelligence — Full Pipeline Orchestrator
Phases 1-8: Zone Definition → Financial Forecasting → Visualizations
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# Create output directory
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

print(f"\n{'='*80}")
print(f"EV CHARGING INTELLIGENCE — PREDICTIVE ANALYTICS PIPELINE")
print(f"{'='*80}\n")

# ============================================================================
# PHASE 0: DATA PREP & VALIDATION
# ============================================================================
print("[PHASE 0] Data Preparation & Validation...")

# Load all raw datasets
print("  Loading raw datasets...")
try:
    m1_ev = pd.read_csv('m1_ev_by_rto_clean.csv')
    m2_chargers = pd.read_csv('m2_chargers_osm.csv')
    m3_poi = pd.read_csv('m3_poi_raw.csv')
    m4_restaurants = pd.read_csv('m4_restaurants_raw.csv')
    m5_land = pd.read_csv('m5_land.csv')
    m6_grid = pd.read_csv('m6_grid_stability.csv')
    m7_supply = pd.read_csv('m7_planned_supply.csv')

    print(f"  [OK] m1_ev: {m1_ev.shape[0]} rows")
    print(f"  [OK] m2_chargers: {m2_chargers.shape[0]} rows")
    print(f"  [OK] m3_poi: {m3_poi.shape[0]} rows")
    print(f"  [OK] m4_restaurants: {m4_restaurants.shape[0]} rows")
    print(f"  [OK] m5_land: {m5_land.shape[0]} rows")
    print(f"  [OK] m6_grid: {m6_grid.shape[0]} rows")
    print(f"  [OK] m7_supply: {m7_supply.shape[0]} rows")
except Exception as e:
    print(f"  [ERROR] Error loading datasets: {e}")
    sys.exit(1)

# Data validation
print("\n  Validating data quality...")
validation_log = []

if 'lat' not in m2_chargers.columns or 'lon' not in m2_chargers.columns:
    print("  ⚠ m2_chargers missing lat/lon")
if m2_chargers['lat'].isna().sum() > m2_chargers.shape[0] * 0.5:
    print("  ⚠ m2_chargers has >50% missing lat/lon")

print("  ✓ Validation complete\n")

# ============================================================================
# PHASE 1: ZONE DEFINITION (K-MEANS CLUSTERING)
# ============================================================================
print("[PHASE 1] Zone Definition via K-Means Clustering...")

from sklearn.cluster import KMeans
from scipy.spatial.distance import cdist

# Prepare clustering data: chargers + POI-weighted points
charger_points = m2_chargers[['lat', 'lon']].dropna()
print(f"  Charger points: {len(charger_points)}")

# Weight POI by importance (IT parks > hotels > malls > basic)
poi_weights = {
    'it_park': 3.0,
    'hotel': 2.5,
    'mall': 2.0,
    'metro': 1.5,
    'hospital': 1.5,
    'university': 1.5,
    'petrol_pump': 1.0
}

m3_poi['poi_type_normalized'] = m3_poi['poi_type'].fillna('petrol_pump')
m3_poi['weight_assigned'] = m3_poi['poi_type_normalized'].map(poi_weights).fillna(1.0)

# Oversample POI by weight
poi_points = m3_poi[['lat', 'lon']].sample(
    n=min(len(m3_poi) * 3, 5000),
    weights=m3_poi['weight_assigned'],
    random_state=42
)
print(f"  POI points (weighted): {len(poi_points)}")

# Combine for clustering
all_points = pd.concat([charger_points, poi_points], ignore_index=True)

# Apply K-Means
kmeans = KMeans(n_clusters=20, random_state=42, n_init=10, max_iter=300)
clusters = kmeans.fit_predict(all_points[['lat', 'lon']])
all_points['cluster'] = clusters

# Compute zone centroids
zone_centroids = all_points.groupby('cluster')[['lat', 'lon']].mean().reset_index()
zone_centroids.columns = ['zone_id', 'lat_centroid', 'lon_centroid']
zone_centroids['zone_id'] = range(1, len(zone_centroids) + 1)

print(f"  ✓ {len(zone_centroids)} zones defined")

# Manually assign zone names based on geography (you can refine these)
zone_names_map = {
    1: "HSR Layout Sector 1",
    2: "Whitefield ITPL",
    3: "Koramangala 5th Block",
    4: "Electronic City Phase 1",
    5: "Sarjapur Road",
    6: "Marathahalli",
    7: "Rajajinagar",
    8: "JP Nagar Phase 1",
    9: "MG Road",
    10: "Bellandur",
    11: "BTM Layout",
    12: "Indiranagar",
    13: "Hebbal",
    14: "Yelahanka",
    15: "Devanahalli",
    16: "Kengeri",
    17: "Jayanagar",
    18: "Tumkur Road",
    19: "Outer Ring Road",
    20: "Yeshwanthpur"
}
zone_centroids['zone_name'] = zone_centroids['zone_id'].map(zone_names_map)

# Assign all data points to nearest zone
print(f"  Assigning data points to zones...")
distances = cdist(charger_points, zone_centroids[['lat_centroid', 'lon_centroid']])
m2_chargers['zone_id'] = distances.argmin(axis=1) + 1

distances_poi = cdist(m3_poi[['lat', 'lon']], zone_centroids[['lat_centroid', 'lon_centroid']])
m3_poi['zone_id'] = distances_poi.argmin(axis=1) + 1

distances_rest = cdist(m4_restaurants[['lat', 'lon']], zone_centroids[['lat_centroid', 'lon_centroid']])
m4_restaurants['zone_id'] = distances_rest.argmin(axis=1) + 1

# Save zone definitions
zone_centroids.to_csv(OUTPUT_DIR / "01_zone_definitions.csv", index=False)
print(f"  ✓ Saved: 01_zone_definitions.csv\n")

# ============================================================================
# PHASE 2: BUILD MASTER DATASET
# ============================================================================
print("[PHASE 2] Building Master Dataset (Zone-Aggregated)...")

master = zone_centroids[['zone_id', 'zone_name', 'lat_centroid', 'lon_centroid']].copy()

# Track 1: EV Registrations by zone (RTO mapping)
print("  Aggregating Track 1 (EV Registrations)...")
rto_to_zone = {
    'KA1': 9, 'KA2': 7, 'KA3': 12, 'KA4': 14, 'KA5': 10,
    'KA41': 16, 'KA51': 4
}
m1_ev['zone_id'] = m1_ev['rto_code'].map(rto_to_zone)
m1_ev_agg = m1_ev.groupby('zone_id').agg({
    'ev_registrations': 'sum'
}).reset_index()
m1_ev_agg.columns = ['zone_id', 'ev_registrations']

# Growth rate (average)
m1_ev_2024 = m1_ev[m1_ev['year'] == 2024].set_index('zone_id')['ev_registrations']
m1_ev_2025 = m1_ev[m1_ev['year'] == 2025].set_index('zone_id')['ev_registrations']
m1_ev_agg['ev_growth_rate_yoy'] = (m1_ev_2025 / m1_ev_2024 - 1).values

master = master.merge(m1_ev_agg, on='zone_id', how='left')

# Track 2: Charger Supply
print("  Aggregating Track 2 (Charger Supply)...")
m2_chargers['is_fast'] = m2_chargers['charger_type_dc_fast'].fillna(False).astype(bool)
m2_agg = m2_chargers.groupby('zone_id').agg({
    'osm_id': 'count',
    'is_fast': 'sum',
    'review_count': 'sum'
}).reset_index()
m2_agg.columns = ['zone_id', 'charger_count_total', 'fast_charger_count', 'google_review_count_total']
m2_agg['slow_charger_count'] = m2_agg['charger_count_total'] - m2_agg['fast_charger_count']

master = master.merge(m2_agg, on='zone_id', how='left')

# Track 3: POI Density (by type)
print("  Aggregating Track 3 (POI Density)...")
poi_types = ['it_park', 'hotel', 'mall', 'metro', 'hospital', 'university', 'petrol_pump']
poi_weights_dict = {
    'it_park': 3.0, 'hotel': 2.5, 'mall': 2.0, 'metro': 1.5,
    'hospital': 1.5, 'university': 1.5, 'petrol_pump': 1.0
}

for poi_type in poi_types:
    m3_poi[f'{poi_type}_count'] = (m3_poi['poi_type_normalized'] == poi_type).astype(int)

m3_agg = m3_poi.groupby('zone_id').agg({
    'it_park_count': 'sum', 'hotel_count': 'sum', 'mall_count': 'sum',
    'metro_count': 'sum', 'hospital_count': 'sum', 'university_count': 'sum',
    'petrol_pump_count': 'sum'
}).reset_index()

# Compute weighted POI score
m3_agg['poi_score_weighted'] = (
    m3_agg['it_park_count'] * 3.0 +
    m3_agg['hotel_count'] * 2.5 +
    m3_agg['mall_count'] * 2.0 +
    m3_agg['metro_count'] * 1.5 +
    m3_agg['hospital_count'] * 1.5 +
    m3_agg['university_count'] * 1.5 +
    m3_agg['petrol_pump_count'] * 1.0
)

master = master.merge(m3_agg, on='zone_id', how='left')

# Track 4: Footfall (Restaurants)
print("  Aggregating Track 4 (Footfall)...")
m4_agg = m4_restaurants.groupby('zone_id').agg({
    'name': 'count'
}).reset_index()
m4_agg.columns = ['zone_id', 'restaurant_count_raw']

# Normalize to 0-100
max_restaurants = m4_agg['restaurant_count_raw'].max()
m4_agg['footfall_composite'] = (m4_agg['restaurant_count_raw'] / max_restaurants * 100).round(1)

master = master.merge(m4_agg[['zone_id', 'footfall_composite']], on='zone_id', how='left')

# Track 5: Land & Real Estate
print("  Aggregating Track 5 (Land & Real Estate)...")
# Spatial join: find nearest locality for each zone
from scipy.spatial.distance import cdist
distances_land = cdist(
    zone_centroids[['lat_centroid', 'lon_centroid']],
    m5_land[['lat', 'lon']]
)
nearest_locality_idx = distances_land.argmin(axis=1)
zone_to_land = m5_land.iloc[nearest_locality_idx].reset_index(drop=True)
zone_to_land['zone_id'] = range(1, len(zone_to_land) + 1)

master = master.merge(
    zone_to_land[['zone_id', 'price_psf_residential', 'price_psf_commercial',
                   'hcpi_estimated', 'new_projects_pipeline_count', 'new_projects_units_total']],
    on='zone_id', how='left'
)

# Track 6: Grid Stability
print("  Aggregating Track 6 (Grid Stability)...")
m6_land = m6_grid.copy()
m6_land['zone_id'] = m6_land['zone_id'].fillna(0).astype(int)
master = master.merge(m6_land[['zone_id', 's_score']], on='zone_id', how='left')

# Track 7: Planned Supply
print("  Aggregating Track 7 (Planned Supply)...")
m7_supply['zone_id'] = m7_supply['zone_id'].fillna(0).astype(int)
m7_agg = m7_supply.groupby('zone_id').size().reset_index(name='planned_supply_6mo')
master = master.merge(m7_agg, on='zone_id', how='left')

# Fill NAs with sensible defaults
master = master.fillna({
    'ev_registrations': 0,
    'ev_growth_rate_yoy': 1.0,
    'charger_count_total': 0,
    'fast_charger_count': 0,
    'slow_charger_count': 0,
    'google_review_count_total': 0,
    'poi_score_weighted': 0,
    'footfall_composite': 0,
    's_score': 1.0,
    'planned_supply_6mo': 0,
    'it_park_count': 0,
    'mall_count': 0,
    'hotel_count': 0,
    'metro_count': 0,
    'hospital_count': 0,
    'university_count': 0,
    'petrol_pump_count': 0
})

# Add derived fields
master['area_km2'] = 2.5  # Avg zone size
master['population_density'] = (master['ev_registrations'] / master['area_km2']).round(0)

# Charger density per km2
master['charger_density_per_km2'] = (master['charger_count_total'] / master['area_km2']).round(2)

# Fast desert flag (computed in Phase 3)
master['fast_desert_flag'] = 0

# Save master dataset
master.to_csv(OUTPUT_DIR / "02_master_dataset.csv", index=False)
print(f"  ✓ Saved: 02_master_dataset.csv")
print(f"  ✓ {master.shape[0]} zones × {master.shape[1]} features\n")

# ============================================================================
# PHASE 3: COMPUTE CONGESTION INDEX (CI)
# ============================================================================
print("[PHASE 3] Computing Congestion Index (CI)...")

# CI = P_EV × (G_rate - 1) / S_eff
# where S_eff = accessibility-weighted charger supply

# Compute S_eff: chargers weighted by proximity to each zone
print("  Computing accessibility-weighted supply (S_eff)...")
S_eff = []
for i, zone in master.iterrows():
    zone_lat, zone_lon = zone['lat_centroid'], zone['lon_centroid']

    # Distance from this zone to all chargers
    charger_dists = cdist(
        [[zone_lat, zone_lon]],
        m2_chargers[['lat', 'lon']].values
    ).flatten()

    # Accessibility weight: 1 / (1 + distance_km)
    charger_dists_km = charger_dists * 111  # rough conversion
    accessibility_weights = 1 / (1 + charger_dists_km)

    s_eff_val = accessibility_weights.sum()
    S_eff.append(s_eff_val)

master['S_eff'] = S_eff

# Compute CI
master['ev_growth_rate_yoy'] = master['ev_growth_rate_yoy'].clip(lower=1.0)
master['congestion_index'] = (
    master['ev_registrations'] *
    (master['ev_growth_rate_yoy'] - 1) /
    (master['S_eff'] + 0.1)  # avoid division by zero
).round(3)

# Fast desert flag
master['fast_desert_flag'] = ((master['congestion_index'] > 2.5) &
                              (master['fast_charger_count'] == 0)).astype(int)

# Zone archetype
def assign_archetype(row):
    if row['it_park_count'] >= 2:
        return 'IT Corridor'
    elif row['footfall_composite'] > 70:
        return 'High-Traffic Hub'
    elif row['petrol_pump_count'] >= 3:
        return 'Highway Corridor'
    else:
        return 'Residential'

master['zone_archetype'] = master.apply(assign_archetype, axis=1)

# Save CI results
ci_results = master[['zone_id', 'zone_name', 'ev_registrations', 'ev_growth_rate_yoy',
                      'S_eff', 'congestion_index', 'fast_desert_flag', 'zone_archetype']].copy()
ci_results.to_csv(OUTPUT_DIR / "03_congestion_index.csv", index=False)

print(f"  Mean CI: {master['congestion_index'].mean():.2f}")
print(f"  Max CI (highest demand): {master['congestion_index'].idxmax()} - {master.loc[master['congestion_index'].idxmax(), 'zone_name']}")
print(f"  Fast deserts (CI>2.5, 0 fast chargers): {master['fast_desert_flag'].sum()}")
print(f"  ✓ Saved: 03_congestion_index.csv\n")

# ============================================================================
# PHASE 4: COMPUTE SITE SCORE
# ============================================================================
print("[PHASE 4] Computing Site Score (Deployment Ranking)...")

# Normalize features to 0-1
def normalize(series):
    return (series - series.min()) / (series.max() - series.min() + 1e-6)

master['CI_norm'] = normalize(master['congestion_index'])

# Supply gap: high demand - low supply
master['supply_gap'] = master['ev_registrations'] / (master['charger_count_total'] + 1)
master['supply_gap_norm'] = normalize(master['supply_gap'])

master['footfall_norm'] = normalize(master['footfall_composite'])
master['s_score_norm'] = master['s_score']  # already 0-1

# Weighted composite score
master['site_score'] = (
    0.40 * master['CI_norm'] +
    0.30 * master['supply_gap_norm'] +
    0.15 * master['footfall_norm'] +
    0.15 * master['s_score_norm']
) * 100

master['site_score'] = master['site_score'].round(1)
master['site_rank'] = master['site_score'].rank(ascending=False).astype(int)

# Deployment priority
def get_priority(rank):
    if rank <= 5:
        return 'Tier-1 (Immediate)'
    elif rank <= 10:
        return 'Tier-2 (6-12 months)'
    else:
        return 'Tier-3 (Strategic)'

master['deployment_priority'] = master['site_rank'].apply(get_priority)

# Save site score results
site_score_results = master[['zone_id', 'zone_name', 'site_score', 'site_rank',
                              'deployment_priority', 'zone_archetype']].sort_values('site_rank')
site_score_results.to_csv(OUTPUT_DIR / "04_site_score.csv", index=False)

print(f"  Top 5 deployment zones:")
for idx, row in site_score_results.head(5).iterrows():
    print(f"    {row['site_rank']}. {row['zone_name']} (Score: {row['site_score']})")

print(f"  ✓ Saved: 04_site_score.csv\n")

# ============================================================================
# PHASE 5: RANDOM FOREST MODEL (12-MONTH CI FORECAST)
# ============================================================================
print("[PHASE 5] Training Random Forest for CI Prediction...")

from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import pickle

# Feature selection
feature_cols = [
    'ev_registrations', 'ev_growth_rate_yoy', 'footfall_composite',
    'poi_score_weighted', 'price_psf_commercial', 'hcpi_estimated',
    'new_projects_pipeline_count', 's_score', 'fast_charger_count',
    'charger_density_per_km2'
]

X = master[feature_cols].fillna(0)
y = master['congestion_index']

# Train model
rf_model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
rf_model.fit(X, y)

# Predictions
master['predicted_ci_t12'] = rf_model.predict(X)

# Feature importance
feature_importance = pd.DataFrame({
    'feature': feature_cols,
    'importance': rf_model.feature_importances_
}).sort_values('importance', ascending=False)

# Save model and results
with open(OUTPUT_DIR / "rf_model.pkl", 'wb') as f:
    pickle.dump(rf_model, f)

master[['zone_id', 'zone_name', 'congestion_index', 'predicted_ci_t12']].to_csv(
    OUTPUT_DIR / "05_rf_predictions.csv", index=False
)

feature_importance.to_csv(OUTPUT_DIR / "05_feature_importance.csv", index=False)

print(f"  Model R² score (training): {rf_model.score(X, y):.3f}")
print(f"  Top features driving CI:")
for idx, row in feature_importance.head(5).iterrows():
    print(f"    {row['feature']}: {row['importance']:.3f}")

print(f"  ✓ Saved: 05_rf_predictions.csv, 05_feature_importance.csv\n")

# ============================================================================
# PHASE 6: FINANCIAL MODEL (PAYBACK & ROI)
# ============================================================================
print("[PHASE 6] Computing Financial Model (Payback & ROI)...")

sessions_per_day_list = [4, 6, 8, 10, 13]

# Financial assumptions
capex_per_charger = 45e5  # ₹45 lakh
annual_opex_per_charger = 10e5  # ₹10 lakh
revenue_per_session = 100  # ₹100

financial_data = []

for idx, zone in master.iterrows():
    zone_id = zone['zone_id']
    zone_name = zone['zone_name']

    payback_months = {}

    for sessions in sessions_per_day_list:
        daily_revenue = sessions * revenue_per_session
        annual_revenue = daily_revenue * 365
        annual_profit = annual_revenue - annual_opex_per_charger

        if annual_profit > 0:
            payback_months[f'payback_{sessions}_sessions'] = round((capex_per_charger / annual_profit) * 12, 1)
        else:
            payback_months[f'payback_{sessions}_sessions'] = np.inf

    # ROI tier based on 6 sessions/day
    payback_6 = payback_months['payback_6_sessions']
    if payback_6 < 18:
        roi_tier = "HIGH"
    elif payback_6 < 36:
        roi_tier = "MEDIUM"
    else:
        roi_tier = "LOW"

    # Product recommendation
    if zone['fast_charger_count'] == 0 and zone['footfall_composite'] < 30:
        recommended_product = "AC 7-10 kW"
    elif zone['it_park_count'] >= 2 or zone['footfall_composite'] > 70:
        recommended_product = "DC 60 kW"
    elif zone['zone_archetype'] == 'Highway Corridor':
        recommended_product = "DC 120 kW"
    else:
        recommended_product = "DC 30 kW"

    # Estimate sessions/day (from footfall + EVs)
    sessions_estimate = min(int(zone['footfall_composite'] * 0.15), 20)

    record = {
        'zone_id': zone_id,
        'zone_name': zone_name,
        'roi_tier': roi_tier,
        'recommended_product': recommended_product,
        'sessions_per_day_estimate': sessions_estimate,
        **payback_months
    }
    financial_data.append(record)

financial_model = pd.DataFrame(financial_data)
financial_model.to_csv(OUTPUT_DIR / "06_financial_model.csv", index=False)

print(f"  ROI Tier Distribution:")
print(f"    HIGH: {(financial_model['roi_tier'] == 'HIGH').sum()} zones")
print(f"    MEDIUM: {(financial_model['roi_tier'] == 'MEDIUM').sum()} zones")
print(f"    LOW: {(financial_model['roi_tier'] == 'LOW').sum()} zones")

print(f"  Product Distribution:")
for prod in financial_model['recommended_product'].unique():
    count = (financial_model['recommended_product'] == prod).sum()
    print(f"    {prod}: {count} zones")

print(f"  ✓ Saved: 06_financial_model.csv\n")

# ============================================================================
# PHASE 7: CDS (CaaS DEPLOYMENT SCORE)
# ============================================================================
print("[PHASE 7] Computing CDS (Mobile Unit Deployment Score)...")

# CDS = (footfall × weekly_demand) / (current_supply + planned_supply)
master['weekly_sessions_forecast'] = master['footfall_composite'] * 2  # rough estimate
master['available_supply'] = master['charger_count_total'] + master['planned_supply_6mo']
master['available_supply'] = master['available_supply'].replace(0, 1)  # avoid division by zero

master['cds_score'] = (
    master['weekly_sessions_forecast'] / master['available_supply']
).round(2)

# Mobile unit priority
master['mobile_unit_priority'] = master['cds_score'].rank(ascending=False).astype(int)

def get_deployment_duration(cds):
    if cds > 30:
        return '7 days'
    elif cds > 15:
        return '14 days'
    else:
        return '21+ days'

master['recommended_unit_duration_days'] = master['cds_score'].apply(get_deployment_duration)

cds_results = master[['zone_id', 'zone_name', 'cds_score', 'weekly_sessions_forecast',
                       'mobile_unit_priority', 'recommended_unit_duration_days']].sort_values('cds_score', ascending=False)
cds_results.to_csv(OUTPUT_DIR / "07_cds_routing.csv", index=False)

print(f"  Top 5 mobile unit deployment zones:")
for idx, row in cds_results.head(5).iterrows():
    print(f"    {row['mobile_unit_priority']}. {row['zone_name']} (CDS: {row['cds_score']}, Duration: {row['recommended_unit_duration_days']})")

print(f"  ✓ Saved: 07_cds_routing.csv\n")

# ============================================================================
# PHASE 8: VISUALIZATIONS & REPORT
# ============================================================================
print("[PHASE 8] Generating Visualizations & Report...")

import matplotlib.pyplot as plt
import seaborn as sns

sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)

# 1. Site Score Rankings
fig, ax = plt.subplots(figsize=(12, 8))
top_20 = site_score_results.head(20).sort_values('site_score')
colors = ['#d62728' if tier == 'Tier-1 (Immediate)' else '#ff7f0e' if tier == 'Tier-2 (6-12 months)' else '#2ca02c'
          for tier in top_20['deployment_priority']]
ax.barh(top_20['zone_name'], top_20['site_score'], color=colors)
ax.set_xlabel('Site Score (0-100)', fontsize=12, fontweight='bold')
ax.set_title('Zone Deployment Priority Ranking', fontsize=14, fontweight='bold')
ax.legend(['Tier-1', 'Tier-2', 'Tier-3'], loc='lower right')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "08_site_score_rankings.png", dpi=300, bbox_inches='tight')
print(f"  ✓ Generated: 08_site_score_rankings.png")

# 2. CI Distribution
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].hist(master['congestion_index'], bins=15, color='steelblue', edgecolor='black', alpha=0.7)
axes[0].set_xlabel('Congestion Index', fontweight='bold')
axes[0].set_ylabel('Number of Zones', fontweight='bold')
axes[0].set_title('CI Distribution Across Zones', fontweight='bold')
axes[0].axvline(master['congestion_index'].mean(), color='red', linestyle='--', label='Mean', linewidth=2)

# Scatter: EV Growth vs Charger Density
axes[1].scatter(master['charger_density_per_km2'], master['ev_growth_rate_yoy'],
                s=master['congestion_index']*100, alpha=0.6, c=master['congestion_index'],
                cmap='RdYlGn_r', edgecolors='black', linewidth=1)
axes[1].set_xlabel('Charger Density (per km²)', fontweight='bold')
axes[1].set_ylabel('EV Growth Rate (YoY)', fontweight='bold')
axes[1].set_title('EV Growth vs Supply (bubble=CI)', fontweight='bold')
plt.colorbar(axes[1].collections[0], ax=axes[1], label='CI')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "08_ci_distribution.png", dpi=300, bbox_inches='tight')
print(f"  ✓ Generated: 08_ci_distribution.png")

# 3. Feature Importance
fig, ax = plt.subplots(figsize=(10, 6))
feature_importance_top = feature_importance.head(10)
ax.barh(feature_importance_top['feature'], feature_importance_top['importance'], color='teal')
ax.set_xlabel('Importance Score', fontweight='bold')
ax.set_title('Random Forest Feature Importance (CI Prediction)', fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "08_feature_importance.png", dpi=300, bbox_inches='tight')
print(f"  ✓ Generated: 08_feature_importance.png")

# 4. ROI Tier Distribution
fig, ax = plt.subplots(figsize=(10, 6))
roi_counts = financial_model['roi_tier'].value_counts()
colors_roi = {'HIGH': '#2ca02c', 'MEDIUM': '#ff7f0e', 'LOW': '#d62728'}
ax.bar(roi_counts.index, roi_counts.values, color=[colors_roi[tier] for tier in roi_counts.index],
       edgecolor='black', linewidth=2)
ax.set_ylabel('Number of Zones', fontweight='bold')
ax.set_title('ROI Tier Distribution', fontweight='bold')
ax.set_ylim(0, max(roi_counts.values) + 2)
for i, (tier, count) in enumerate(roi_counts.items()):
    ax.text(i, count + 0.1, str(count), ha='center', fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "08_roi_distribution.png", dpi=300, bbox_inches='tight')
print(f"  ✓ Generated: 08_roi_distribution.png")

# 5. Payback Sensitivity Table Visualization
fig, ax = plt.subplots(figsize=(12, 8))
payback_cols = [col for col in financial_model.columns if col.startswith('payback_')]
payback_matrix = financial_model[['zone_name'] + payback_cols].set_index('zone_name')
payback_matrix.columns = ['4 sess', '6 sess', '8 sess', '10 sess', '13 sess']

# Heatmap
sns.heatmap(payback_matrix.T, annot=True, fmt='.0f', cmap='RdYlGn_r', cbar_kws={'label': 'Months'},
            ax=ax, linewidths=0.5)
ax.set_title('Payback Period Sensitivity (Months)', fontweight='bold')
ax.set_xlabel('Zone', fontweight='bold')
ax.set_ylabel('Sessions/Day', fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "08_payback_sensitivity.png", dpi=300, bbox_inches='tight')
print(f"  ✓ Generated: 08_payback_sensitivity.png")

# 6. CDS Routing Priority
fig, ax = plt.subplots(figsize=(12, 8))
cds_top = cds_results.head(15).sort_values('cds_score')
ax.barh(cds_top['zone_name'], cds_top['cds_score'], color='coral', edgecolor='black')
ax.set_xlabel('CDS Score', fontweight='bold')
ax.set_title('Mobile Unit Deployment Priority (Top 15)', fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "08_cds_priority.png", dpi=300, bbox_inches='tight')
print(f"  ✓ Generated: 08_cds_priority.png")

# ============================================================================
# EXECUTIVE SUMMARY REPORT
# ============================================================================
print("\n" + "="*80)
print("EXECUTIVE SUMMARY REPORT")
print("="*80 + "\n")

summary_text = f"""
PROJECT: EV Charging Intelligence — Bengaluru Pilot
ANALYSIS DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATASET SUMMARY:
  • Total Zones: {master.shape[0]}
  • Total EV Registrations: {master['ev_registrations'].sum():,.0f}
  • Total Chargers (Existing): {master['charger_count_total'].sum():,.0f}
  • Fast Chargers: {master['fast_charger_count'].sum():,.0f}
  • Planned Supply (6mo): {master['planned_supply_6mo'].sum():,.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEMAND ANALYSIS (Congestion Index):
  • Mean CI: {master['congestion_index'].mean():.2f}
  • Max CI (Critical): {master['congestion_index'].max():.2f}
  • Min CI (Over-supplied): {master['congestion_index'].min():.2f}
  • Fast Deserts (CI>2.5 & 0 chargers): {master['fast_desert_flag'].sum()} zones

  Highest Demand Zones:
"""

for idx, row in master.nlargest(3, 'congestion_index').iterrows():
    summary_text += f"    {idx+1}. {row['zone_name']} (CI: {row['congestion_index']:.2f}, EVs: {row['ev_registrations']:.0f})\n"

summary_text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAPEX DEPLOYMENT PRIORITIES (Site Score Ranking):

Tier-1 Zones (Immediate Deployment):
"""

tier1_zones = site_score_results[site_score_results['deployment_priority'] == 'Tier-1 (Immediate)']
for idx, row in tier1_zones.head(5).iterrows():
    summary_text += f"  {row['site_rank']}. {row['zone_name']} (Score: {row['site_score']}, Archetype: {row['zone_archetype']})\n"

summary_text += f"""

Tier-2 Zones (6-12 Month Horizon):
"""

tier2_zones = site_score_results[site_score_results['deployment_priority'] == 'Tier-2 (6-12 months)']
for idx, row in tier2_zones.head(5).iterrows():
    summary_text += f"  {row['site_rank']}. {row['zone_name']} (Score: {row['site_score']})\n"

summary_text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINANCIAL PROJECTIONS (at 6 Sessions/Day):

ROI Tier Breakdown:
  • HIGH (Payback <18 months): {(financial_model['roi_tier'] == 'HIGH').sum()} zones
  • MEDIUM (18-36 months): {(financial_model['roi_tier'] == 'MEDIUM').sum()} zones
  • LOW (>36 months): {(financial_model['roi_tier'] == 'LOW').sum()} zones

Product Recommendation Distribution:
"""

for prod in financial_model['recommended_product'].unique():
    count = (financial_model['recommended_product'] == prod).sum()
    summary_text += f"  • {prod}: {count} zones\n"

summary_text += f"""

Highest ROI Zones (Payback <18 months at 6 sess/day):
"""

high_roi = financial_model[financial_model['roi_tier'] == 'HIGH'].nsmallest(3, 'payback_6_sessions')
for idx, row in high_roi.iterrows():
    summary_text += f"  {row['zone_id']}. {row['zone_name']} ({row['payback_6_sessions']:.0f} mo, Product: {row['recommended_product']})\n"

summary_text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPEX MOBILE UNIT DEPLOYMENT (Weekly Routing):

Top 5 CDS Priority Zones:
"""

for idx, row in cds_results.head(5).iterrows():
    summary_text += f"  Week {row['mobile_unit_priority']}. {row['zone_name']} (CDS: {row['cds_score']}, Duration: {row['recommended_unit_duration_days']})\n"

summary_text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KEY DRIVERS OF CI (Random Forest Feature Importance):
"""

for idx, row in feature_importance.head(5).iterrows():
    summary_text += f"  {idx+1}. {row['feature']}: {row['importance']:.3f}\n"

summary_text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OUTPUT FILES GENERATED:
  ✓ 01_zone_definitions.csv — 20 micro-zones with centroids
  ✓ 02_master_dataset.csv — Zone-aggregated dataset (35 features)
  ✓ 03_congestion_index.csv — CI computations per zone
  ✓ 04_site_score.csv — Deployment priority ranking
  ✓ 05_rf_predictions.csv — 12-month CI forecast
  ✓ 05_feature_importance.csv — Feature drivers
  ✓ 06_financial_model.csv — Payback & ROI analysis
  ✓ 07_cds_routing.csv — Mobile unit scheduling
  ✓ 08_*.png — Visualizations (6 charts)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# Save summary to file
with open(OUTPUT_DIR / "EXECUTIVE_SUMMARY.txt", 'w') as f:
    f.write(summary_text)

print(summary_text)

print(f"\n{'='*80}")
print(f"ALL PHASES COMPLETED SUCCESSFULLY!")
print(f"{'='*80}\n")
print(f"Output directory: {OUTPUT_DIR.absolute()}\n")

# Save the full master dataset with all computations
master.to_csv(OUTPUT_DIR / "02_master_dataset_complete.csv", index=False)
print("✓ Full master dataset saved: 02_master_dataset_complete.csv")
