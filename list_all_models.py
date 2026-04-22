import boto3
import streamlit as st

region = st.secrets['aws']['region']
access_key = st.secrets['aws']['access_key_id']
secret_key = st.secrets['aws']['secret_access_key']

print(f"🔍 TOUS les modèles Bedrock disponibles dans {region}...\n")

try:
    bedrock = boto3.client(
        'bedrock',
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    
    response = bedrock.list_foundation_models()
    
    anthropic_models = [m for m in response['modelSummaries'] if m['providerName'] == 'Anthropic']
    
    print(f"📋 {len(anthropic_models)} MODÈLES ANTHROPIC DISPONIBLES :\n")
    
    for model in anthropic_models:
        print(f"✅ {model['modelName']}")
        print(f"   Model ID: {model['modelId']}")
        print(f"   Input modalities: {model.get('inputModalities', [])}")
        print(f"   Output modalities: {model.get('outputModalities', [])}")
        print()
    
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()