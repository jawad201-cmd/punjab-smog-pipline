# locations.py

# The "Macro Box" for NASA (Covers all Punjab + Islamabad)
# Format: West, South, East, North
PUNJAB_MACRO_BBOX = "69.0,27.5,75.5,34.5"

# Complete Dictionary of 42 Districts (41 Punjab + 1 Federal)
DISTRICTS = {
    # --- 1. FEDERAL CAPITAL ---
    "Islamabad":        {"lat": 33.6844, "lon": 73.0479},

    # --- 2. RAWALPINDI DIVISION ---
    "Rawalpindi":       {"lat": 33.5651, "lon": 73.0169},
    "Attock":           {"lat": 33.7660, "lon": 72.3609},
    "Chakwal":          {"lat": 32.9328, "lon": 72.8548},
    "Jhelum":           {"lat": 32.9405, "lon": 73.7276},
    "Murree":           {"lat": 33.9070, "lon": 73.3943}, # New District
    "Talagang":         {"lat": 32.9297, "lon": 72.4146}, # New District

    # --- 3. GUJRANWALA DIVISION ---
    "Gujranwala":       {"lat": 32.1603, "lon": 74.1883},
    "Sialkot":          {"lat": 32.4945, "lon": 74.5229},
    "Narowal":          {"lat": 32.0998, "lon": 74.8744},

    # --- 4. GUJRAT DIVISION ---
    "Gujrat":           {"lat": 32.5738, "lon": 74.0802},
    "Hafizabad":        {"lat": 32.0679, "lon": 73.6851},
    "Mandi Bahauddin":  {"lat": 32.5870, "lon": 73.4912},
    "Wazirabad":        {"lat": 32.4432, "lon": 74.1200}, # New District

    # --- 5. LAHORE DIVISION ---
    "Lahore":           {"lat": 31.5204, "lon": 74.3587},
    "Kasur":            {"lat": 31.1187, "lon": 74.4507},
    "Sheikhupura":      {"lat": 31.7131, "lon": 73.9783},
    "Nankana Sahib":    {"lat": 31.4492, "lon": 73.7124},

    # --- 6. FAISALABAD DIVISION ---
    "Faisalabad":       {"lat": 31.4504, "lon": 73.1350},
    "Jhang":            {"lat": 31.2780, "lon": 72.3118},
    "Toba Tek Singh":   {"lat": 30.9709, "lon": 72.4827},
    "Chiniot":          {"lat": 31.7200, "lon": 72.9789},

    # --- 7. SARGODHA DIVISION ---
    "Sargodha":         {"lat": 32.0836, "lon": 72.6711},
    "Khushab":          {"lat": 32.2952, "lon": 72.3489},
    "Mianwali":         {"lat": 32.5839, "lon": 71.5370},
    "Bhakkar":          {"lat": 31.6252, "lon": 71.0657},

    # --- 8. SAHIWAL DIVISION ---
    "Sahiwal":          {"lat": 30.6682, "lon": 73.1114},
    "Okara":            {"lat": 30.8090, "lon": 73.4508},
    "Pakpattan":        {"lat": 30.3432, "lon": 73.3894},

    # --- 9. MULTAN DIVISION ---
    "Multan":           {"lat": 30.1575, "lon": 71.5249},
    "Khanewal":         {"lat": 30.3017, "lon": 71.9321},
    "Lodhran":          {"lat": 29.5467, "lon": 71.6276},
    "Vehari":           {"lat": 30.0333, "lon": 72.3500},

    # --- 10. D.G. KHAN DIVISION ---
    "Dera Ghazi Khan":  {"lat": 30.0489, "lon": 70.6455},
    "Rajanpur":         {"lat": 29.1035, "lon": 70.3250},
    "Muzaffargarh":     {"lat": 30.0754, "lon": 71.1921},
    "Layyah":           {"lat": 30.9613, "lon": 70.9390},
    "Kot Addu":         {"lat": 30.4735, "lon": 70.9664}, # New District
    "Taunsa":           {"lat": 30.7048, "lon": 70.6505}, # New District (Taunsa Sharif)

    # --- 11. BAHAWALPUR DIVISION ---
    "Bahawalpur":       {"lat": 29.3544, "lon": 71.6911},
    "Bahawalnagar":     {"lat": 29.9987, "lon": 73.2536},
    "Rahim Yar Khan":   {"lat": 28.4212, "lon": 70.2989}
}