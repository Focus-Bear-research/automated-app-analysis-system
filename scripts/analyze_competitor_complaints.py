import os
import pandas as pd
import json

def analyze_negative_complaints():
    # 1. Define paths to review datasets using improved sentiment data
    reviews_path = 'automated-app-analysis-system/data/curated/reviews_with_improved_sentiment.csv'
    if not os.path.exists(reviews_path):
        reviews_path = 'automated-app-analysis-system/data/curated/reviews_with_ml_sentiment.csv'
    if not os.path.exists(reviews_path):
        reviews_path = 'automated-app-analysis-system/data/curated/reviews.csv'
        
    if not os.path.exists(reviews_path):
        print(f"Error: Review data file not found at {reviews_path}")
        return

    df = pd.read_csv(reviews_path)
    print(f"Successfully loaded {len(df)} review records.")

    # 2. Filter negative reviews (rating <= 2 or negative sentiment)
    if 'rating' in df.columns:
        df_neg = df[df['rating'] <= 2].copy()
    elif 'sentiment' in df.columns:
        df_neg = df[df['sentiment'].astype(str).str.lower() == 'negative'].copy()
    else:
        df_neg = df.head(0)

    print(f"Filtered negative reviews count: {len(df_neg)}")

    # 3. Define fixed complaint themes and keyword mappings
    themes = {
        "pricing": ["price", "expensive", "subscription", "paywall", "cost", "money", "free"],
        "bugs_crashes": ["bug", "crash", "glitch", "freeze", "broken", "stopped working", "error"],
        "too_easy_to_bypass": ["bypass", "cheat", "easy to disable", "loophole", "uninstall"],
        "too_rigid": ["rigid", "strict", "inflexible", "forced", "annoying rules"],
        "notifications": ["notification", "reminder", "alert", "spam", "too many alarms"],
        "onboarding": ["onboarding", "signup", "register", "tutorial", "stuck", "login"],
        "sync": ["sync", "syncing", "cloud", "device", "connection", "offline"],
        "missing_feature": ["missing", "wish", "lack", "needs", "would be great if", "add a"]
    }

    # 4. Keyword-based theme classification helper function
    def classify_theme(text):
        text_lower = str(text).lower()
        matched_themes = []
        for theme, keywords in themes.items():
            if any(kw in text_lower for kw in keywords):
                matched_themes.append(theme)
        return matched_themes if matched_themes else ["other"]

    text_col = 'body' if 'body' in df_neg.columns else (df_neg.columns[3] if len(df_neg.columns) > 3 else 'content')
    df_neg['complaint_themes'] = df_neg[text_col].apply(classify_theme)

    # 5. Explode dataframe and compute per-app and per-theme counts
    df_exploded = df_neg.explode('complaint_themes')
    
    app_col = 'app_key' if 'app_key' in df_exploded.columns else 'appId'
    summary_counts = df_exploded.groupby([app_col, 'complaint_themes']).size().reset_index(name='complaint_count')

    # 6. Extract 3 example quotes per theme and store as JSON string in the report
    quotes_dict = {}
    for theme in themes.keys():
        theme_rows = df_exploded[df_exploded['complaint_themes'] == theme]
        sample_quotes = theme_rows[text_col].dropna().head(3).tolist()
        quotes_dict[theme] = json.dumps(sample_quotes, ensure_ascii=False)

    summary_counts['example_quotes'] = summary_counts['complaint_themes'].map(quotes_dict)

    # 7. Export summary report
    os.makedirs('data/curated', exist_ok=True)
    output_summary = 'automated-app-analysis-system/data/curated/competitor_complaints_summary.csv'
    summary_counts.to_csv(output_summary, index=False)
    print(f"Summary complaints report with quotes successfully saved to: {output_summary}")
    print(summary_counts.head(10))

if __name__ == "__main__":
    analyze_negative_complaints()