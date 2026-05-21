import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

VAHAN_URL = "https://vahan.parivahan.gov.in/vahan4dashboard/vahan/view/reportview.xhtml"

def init_driver():
    options = webdriver.ChromeOptions()
    # Comment out headless while testing so you can see what's happening
    # options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    return driver

def scrape_month(driver, year, month):
    wait = WebDriverWait(driver, 30)  # playbook says use 30s, not 10s

    try:
        # Wait for state dropdown and select Karnataka
        state_dd = wait.until(EC.element_to_be_clickable((By.ID, "selectedStateId")))
        Select(state_dd).select_by_visible_text("Karnataka")
        time.sleep(1)

        # Select fuel type = ELECTRIC(BOV)
        fuel_dd = wait.until(EC.element_to_be_clickable((By.ID, "selectedFuelTypeId")))
        Select(fuel_dd).select_by_visible_text("ELECTRIC(BOV)")
        time.sleep(1)

        # Select year
        year_dd = wait.until(EC.element_to_be_clickable((By.ID, "selectedYearId")))
        Select(year_dd).select_by_visible_text(str(year))
        time.sleep(1)

        # Select month
        month_dd = wait.until(EC.element_to_be_clickable((By.ID, "selectedMonthId")))
        Select(month_dd).select_by_visible_text(str(month))
        time.sleep(1)

        # Click search — dismiss any overlay first if it appears
        try:
            overlay = driver.find_element(By.CSS_SELECTOR, ".ui-dialog-footer button")
            overlay.click()
            time.sleep(1)
        except:
            pass  # no overlay, that's fine

        search_btn = wait.until(EC.element_to_be_clickable((By.ID, "yieldButton")))
        search_btn.click()

        # Wait for results table to populate
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(@id,'yieldTable')]//tbody/tr")
        ))
        time.sleep(2)

        # Extract table
        tables = pd.read_html(driver.page_source)
        if tables:
            df = tables[0]
            df["year"] = year
            df["month"] = month
            df["state"] = "Karnataka"
            df["fuel_type"] = "ELECTRIC(BOV)"
            return df
        else:
            print(f"  No table found for {year}-{month:02d}")
            return None

    except Exception as e:
        print(f"  Error for {year}-{month:02d}: {e}")
        return None

def main():
    driver = init_driver()
    driver.get(VAHAN_URL)
    time.sleep(3)  # let page fully load on first visit

    all_rows = []
    years = range(2020, 2026)
    months = range(1, 13)

    for year in years:
        for month in months:
            print(f"Scraping {year}-{month:02d}...")
            df = scrape_month(driver, year, month)
            if df is not None:
                all_rows.append(df)
                # Save after every successful pull so crashes don't lose progress
                pd.concat(all_rows).to_csv("m1_ev_monthly_partial.csv", index=False)
                print(f"  Saved. Running total: {len(all_rows)} months.")

            # Rate limit: 3–5 seconds between queries as per playbook
            time.sleep(4)

    driver.quit()

    if all_rows:
        final = pd.concat(all_rows, ignore_index=True)
        final.to_csv("m1_ev_monthly.csv", index=False)
        print(f"\nDone. {len(final)} rows saved to m1_ev_monthly.csv")
    else:
        print("No data collected.")

if __name__ == "__main__":
    main()