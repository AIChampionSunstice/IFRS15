"""
Test connexion AWS - Bucket S3, Textract, Bedrock
"""

import streamlit as st
import boto3
import json

print("🔍 Test connexion AWS...\n")

try:
    # Charger secrets
    region = st.secrets['aws']['region']
    bucket_name = st.secrets['aws']['bucket_name']
    access_key = st.secrets['aws']['access_key_id']
    secret_key = st.secrets['aws']['secret_access_key']
    
    print(f"✅ Secrets chargés")
    print(f"   Région: {region}")
    print(f"   Bucket: {bucket_name}")
    print(f"   Access Key: {access_key[:10]}...\n")
    
    # Test S3
    print("🪣 Test S3...")
    s3 = boto3.client(
        's3',
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    
    # Upload test
    s3.put_object(
        Bucket=bucket_name,
        Key='test.txt',
        Body=b'Hello IFRS15 Test'
    )
    print(f"✅ Upload test.txt OK")
    
    # List
    response = s3.list_objects_v2(Bucket=bucket_name)
    files = [obj['Key'] for obj in response.get('Contents', [])]
    print(f"✅ Fichiers dans bucket: {files}\n")
    
    # Test Textract
    print("📄 Test Textract...")
    textract = boto3.client(
        'textract',
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    print(f"✅ Textract client OK\n")
    
    # Test Bedrock
    print("🤖 Test Bedrock Claude Opus 4.7...")
    bedrock = boto3.client(
        'bedrock-runtime',
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Dis juste 'AWS Test OK'"}]
    }
    
    response = bedrock.invoke_model(
        modelId='global.anthropic.claude-opus-4-6-v1'
        body=json.dumps(request_body)
    )
    
    response_body = json.loads(response['body'].read())
    message = response_body['content'][0]['text']
    
    print(f"Claude répond: {message}\n")
    
    print("TOUS LES TESTS PASSÉS !\n")
    print("Tu peux maintenant analyser des contrats !\n")
    
except Exception as e:
    print(f"\n❌ ERREUR: {str(e)}\n")
    import traceback
    traceback.print_exc()