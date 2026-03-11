import os
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv

def upload_to_blob(local_file_path, container_name="test"):
    """
    Uploads a local file to Azure Blob Storage.
    Creates the container if it doesn't exist.
    Returns the URL of the uploaded blob.
    """
    load_dotenv()
    
    # Extract credentials from .env (matching extraction_service.py logic)
    account_name = os.getenv("AccountName", "").strip(";")
    account_key = os.getenv("AccountKey", "").split(";")[0]
    
    if not account_name or not account_key:
        raise ValueError("Missing Blob Storage credentials (AccountName/AccountKey) in .env")

    connection_string = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # 1. Ensure container exists
        container_client = blob_service_client.get_container_client(container_name)
        if not container_client.exists():
            print(f"Container '{container_name}' not found. Creating...")
            container_client.create_container()
        
        # 2. Upload the file
        blob_name = os.path.basename(local_file_path)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        print(f"Uploading {local_file_path} to blob {blob_name}...")
        with open(local_file_path, "rb") as data:
            # Set content type for Excel files if possible
            content_settings = None
            if local_file_path.endswith((".xlsx", ".xltx", ".xlsm")):
                content_settings = ContentSettings(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            
            blob_client.upload_blob(data, overwrite=True, content_settings=content_settings)
        
        blob_url = blob_client.url
        print(f"Upload successful! URL: {blob_url}")
        return blob_url

    except Exception as e:
        print(f"Error during blob upload: {e}")
        raise e

if __name__ == "__main__":
    # Specify the local file path here
    local_path = r"C:\AI-projects\afg_agno\AFGEstimateAnalyser\waterfall_test.xltx"
    local_path = os.getenv("EXCEL_SOURCE_FILE", "").strip()
    
    if local_path and os.path.exists(local_path):
        upload_to_blob(local_path)
    else:
        print(f"Path not found or not set in .env: {local_path}")
