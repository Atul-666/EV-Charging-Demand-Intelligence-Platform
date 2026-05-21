import pandas as pd

df = pd.read_csv("m1_EV_Registrations_Bengaluru.csv")

# reshape
df_long = df.melt(id_vars=["Region"], 
                  var_name="year", 
                  value_name="ev_registrations")

# split region into name + code
df_long["rto_code"] = df_long["Region"].str.extract(r'(KA\d+)')
df_long["rto_name"] = df_long["Region"].str.replace(r'-\s*KA\d+', '', regex=True)

# reorder
df_final = df_long[["rto_code", "rto_name", "year", "ev_registrations"]]

df_final.to_csv("m1_ev_by_rto_clean.csv", index=False)

print(df_final.head())