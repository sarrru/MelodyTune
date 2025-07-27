import pickle
import pandas as pd

# Load the pickle file
with open("music_recommender_components.pkl", "rb") as f:
    components = pickle.load(f)

# Extract the data
data_lookup = components["data"]

# Add Kathmandu/Nepali classification
data_lookup['language'] = data_lookup['primary_artist'].apply(
    lambda x: 'Nepali' if x in ['VTEN', 'Neetesh Jung Kunwar', 'Swoopna Suman'] else 'English'
)

data_lookup['region'] = data_lookup['language'].apply(
    lambda x: 'Kathmandu' if x == 'Nepali' else 'Global'
)

# Save updated dataset back into the pickle file
components["data"] = data_lookup
with open("music_recommender_components.pkl", "wb") as f:
    pickle.dump(components, f)

# Confirm changes
print(data_lookup[['track_name', 'primary_artist', 'language', 'region']].head(10))
