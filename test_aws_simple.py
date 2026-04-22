import boto3

print("Test connexion AWS...")
try:
    # Vérifier les credentials
    sts = boto3.client('sts', region_name='us-east-1')
    identity = sts.get_caller_identity()
    print(f"✅ Connecté en tant que: {identity['Arn']}")
    print(f"Account ID: {identity['Account']}")
except Exception as e:
    print(f"❌ Erreur: {e}")