import os
import yaml
import pandas as pd

def validate_llm_features_advanced():
    taxonomy_path = 'llm/taxonomy.yml'
    features_path = 'data/curated/features_extracted_all.csv'
    
    if not os.path.exists(taxonomy_path) or not os.path.exists(features_path):
        print("Error: Required taxonomy or feature files not found.")
        return

    # Load taxonomy framework including positive keyword rules
    with open(taxonomy_path, 'r', encoding='utf-8') as f:
        taxonomy_data = yaml.safe_load(f)
    
    features_taxonomy = taxonomy_data.get('features', {})
    
    df_features = pd.read_csv(features_path)
    feature_col = 'features_list' if 'features_list' in df_features.columns else df_features.columns[4]

    discrepancies = []
    for index, row in df_features.iterrows():
        app_id = row.get('appId', row.get('app_key', f"row_{index}"))
        features_text = str(row.get(feature_col, ''))
        
        extracted_features = [f.strip().lower() for f in features_text.replace(';', ',').split(',') if f.strip()]
        
        for feat in extracted_features:
            matched_category = None
            
            for cat_name, cat_details in features_taxonomy.items():
                if isinstance(cat_details, dict):
                    positive_keywords = cat_details.get('positive', [])
                    if any(kw.lower() in feat or feat in kw.lower() for kw in positive_keywords):
                        matched_category = cat_name
                        break
            
            status = f"Valid ({matched_category})" if matched_category else "Mismatch / Not in Taxonomy"
            discrepancies.append({
                'app_id': app_id,
                'tested_feature': feat,
                'status': status
            })

    df_result = pd.DataFrame(discrepancies)
    os.makedirs('data/curated', exist_ok=True)
    report_path = 'data/curated/qa_taxonomy_alignment_report.csv'
    df_result.to_csv(report_path, index=False)
    
    print(f"Refined QA report successfully saved to: {report_path}")
    print(df_result.head(15))

if __name__ == "__main__":
    validate_llm_features_advanced()