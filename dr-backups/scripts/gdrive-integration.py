#!/usr/bin/env python3

"""
Google Drive Integration Module for DR System
Handles authentication, file uploads, and management for Google Drive backups
"""

import os
import sys
import json
import pickle
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import time
from datetime import datetime

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except ImportError as e:
    print(f"ERROR: Missing required Google Drive dependencies: {e}")
    print("Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client tenacity")
    sys.exit(1)

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GoogleDriveBackup:
    """Google Drive backup integration for DR system"""
    
    def __init__(self, config_dict: Dict[str, str]):
        """Initialize Google Drive backup client
        
        Args:
            config_dict: Configuration dictionary with Google Drive settings
        """
        self.config = config_dict
        self.credentials_file = config_dict.get('GDRIVE_CREDENTIALS_FILE')
        self.token_file = config_dict.get('GDRIVE_TOKEN_FILE')
        self.client_id = config_dict.get('GDRIVE_CLIENT_ID')
        self.client_secret = config_dict.get('GDRIVE_CLIENT_SECRET')
        self.folder_name = config_dict.get('GDRIVE_FOLDER_NAME', 'DR-Backups')
        # Parse chunk size, removing any comments
        chunk_size_str = config_dict.get('GDRIVE_UPLOAD_CHUNK_SIZE', '262144')
        # Remove comments and quotes
        chunk_size_str = chunk_size_str.split('#')[0].strip().strip('"').strip("'")
        self.chunk_size = int(chunk_size_str)
        
        self.service = None
        self.folder_id = None
        self.logger = logging.getLogger(__name__)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(message)s'
        )
    
    def authenticate(self) -> bool:
        """Authenticate with Google Drive API
        
        Returns:
            bool: True if authentication successful, False otherwise
        """
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                self.logger.warning(f"Could not load existing token: {e}")
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self.logger.info("Refreshed Google Drive credentials")
                except Exception as e:
                    self.logger.error(f"Failed to refresh credentials: {e}")
                    creds = None
            
            if not creds:
                # Check for credentials file first
                if not os.path.exists(self.credentials_file):
                    # Create credentials file from environment variables
                    if self.client_id and self.client_secret:
                        credentials_data = {
                            "installed": {
                                "client_id": self.client_id,
                                "client_secret": self.client_secret,
                                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                "token_uri": "https://oauth2.googleapis.com/token",
                                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                                "redirect_uris": ["http://localhost"]
                            }
                        }
                        
                        os.makedirs(os.path.dirname(self.credentials_file), exist_ok=True)
                        with open(self.credentials_file, 'w') as f:
                            json.dump(credentials_data, f)
                        self.logger.info(f"Created credentials file: {self.credentials_file}")
                    else:
                        self.logger.error("No Google Drive credentials available")
                        return False
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                    self.logger.info("Completed Google Drive OAuth flow")
                except Exception as e:
                    self.logger.error(f"OAuth flow failed: {e}")
                    return False
            
            # Save credentials for next run
            try:
                os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                self.logger.info(f"Saved Google Drive token: {self.token_file}")
            except Exception as e:
                self.logger.error(f"Failed to save token: {e}")
        
        try:
            self.service = build('drive', 'v3', credentials=creds)
            self.logger.info("Google Drive API service initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to build Google Drive service: {e}")
            return False
    
    def get_or_create_folder(self) -> Optional[str]:
        """Get or create the backup folder in Google Drive
        
        Returns:
            str: Folder ID if successful, None otherwise
        """
        if self.folder_id:
            return self.folder_id
        
        try:
            # Search for existing folder
            results = self.service.files().list(
                q=f"name='{self.folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.folder_id = folders[0]['id']
                self.logger.info(f"Found existing backup folder: {self.folder_name} (ID: {self.folder_id})")
                return self.folder_id
            
            # Create new folder
            folder_metadata = {
                'name': self.folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            self.folder_id = folder.get('id')
            self.logger.info(f"Created backup folder: {self.folder_name} (ID: {self.folder_id})")
            return self.folder_id
            
        except HttpError as e:
            self.logger.error(f"Failed to get/create folder: {e}")
            return None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(HttpError)
    )
    def upload_file(self, local_path: str, remote_name: Optional[str] = None, description: str = "") -> Optional[str]:
        """Upload file to Google Drive with retry logic
        
        Args:
            local_path: Path to local file
            remote_name: Name for file in Google Drive (defaults to filename)
            description: File description
            
        Returns:
            str: File ID if successful, None otherwise
        """
        if not os.path.exists(local_path):
            self.logger.error(f"Local file not found: {local_path}")
            return None
        
        if not self.service:
            self.logger.error("Google Drive service not initialized")
            return None
        
        folder_id = self.get_or_create_folder()
        if not folder_id:
            self.logger.error("Could not get/create backup folder")
            return None
        
        if not remote_name:
            remote_name = os.path.basename(local_path)
        
        file_size = os.path.getsize(local_path)
        self.logger.info(f"Uploading {remote_name} ({file_size:,} bytes) to Google Drive...")
        
        try:
            # File metadata
            file_metadata = {
                'name': remote_name,
                'parents': [folder_id],
                'description': description or f"DR backup uploaded on {datetime.now().isoformat()}"
            }
            
            # Use resumable upload for large files
            media = MediaFileUpload(
                local_path,
                resumable=True,
                chunksize=self.chunk_size
            )
            
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size,createdTime'
            )
            
            response = None
            upload_start = time.time()
            
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    self.logger.info(f"Upload progress: {progress}%")
            
            upload_time = time.time() - upload_start
            file_id = response.get('id')
            
            self.logger.info(f"Successfully uploaded {remote_name} (ID: {file_id}) in {upload_time:.1f}s")
            return file_id
            
        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error("Google Drive quota exceeded or permissions denied")
            else:
                self.logger.error(f"Upload failed with HTTP error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            raise
    
    def list_files(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List files in the backup folder
        
        Args:
            limit: Maximum number of files to return
            
        Returns:
            List of file information dictionaries
        """
        if not self.service:
            self.logger.error("Google Drive service not initialized")
            return []
        
        folder_id = self.get_or_create_folder()
        if not folder_id:
            return []
        
        try:
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                orderBy="createdTime desc",
                pageSize=limit,
                fields="files(id,name,size,createdTime,modifiedTime,description)"
            ).execute()
            
            return results.get('files', [])
            
        except HttpError as e:
            self.logger.error(f"Failed to list files: {e}")
            return []
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file from Google Drive
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.service:
            self.logger.error("Google Drive service not initialized")
            return False
        
        try:
            self.service.files().delete(fileId=file_id).execute()
            self.logger.info(f"Deleted file from Google Drive: {file_id}")
            return True
        except HttpError as e:
            self.logger.error(f"Failed to delete file {file_id}: {e}")
            return False
    
    def download_file(self, file_id: str, local_path: str) -> bool:
        """Download file from Google Drive
        
        Args:
            file_id: Google Drive file ID
            local_path: Local path to save file
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.service:
            self.logger.error("Google Drive service not initialized")
            return False
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as fh:
                downloader = request.execute()
                fh.write(downloader)
            
            self.logger.info(f"Downloaded file from Google Drive: {local_path}")
            return True
            
        except HttpError as e:
            self.logger.error(f"Failed to download file {file_id}: {e}")
            return False
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get Google Drive storage usage information
        
        Returns:
            Dictionary with storage usage information
        """
        if not self.service:
            return {"error": "Service not initialized"}
        
        try:
            about = self.service.about().get(fields="storageQuota,user").execute()
            quota = about.get('storageQuota', {})
            
            return {
                "total": int(quota.get('limit', 0)),
                "used": int(quota.get('usage', 0)),
                "available": int(quota.get('limit', 0)) - int(quota.get('usage', 0)),
                "user_email": about.get('user', {}).get('emailAddress', 'Unknown')
            }
            
        except HttpError as e:
            self.logger.error(f"Failed to get storage usage: {e}")
            return {"error": str(e)}
    
    def cleanup_old_backups(self, retention_days: int = 90) -> int:
        """Clean up old backup files
        
        Args:
            retention_days: Number of days to keep backups
            
        Returns:
            int: Number of files deleted
        """
        if not self.service:
            self.logger.error("Google Drive service not initialized")
            return 0
        
        folder_id = self.get_or_create_folder()
        if not folder_id:
            return 0
        
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        cutoff_str = cutoff_date.isoformat() + 'Z'
        
        try:
            # Find old files
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false and createdTime < '{cutoff_str}'",
                fields="files(id,name,createdTime)"
            ).execute()
            
            old_files = results.get('files', [])
            deleted_count = 0
            
            for file_info in old_files:
                if self.delete_file(file_info['id']):
                    deleted_count += 1
                    self.logger.info(f"Deleted old backup: {file_info['name']}")
            
            self.logger.info(f"Cleaned up {deleted_count} old backup files")
            return deleted_count
            
        except HttpError as e:
            self.logger.error(f"Failed to cleanup old backups: {e}")
            return 0


def main():
    """CLI interface for Google Drive operations"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Google Drive backup operations')
    parser.add_argument('--config', default='../config/dr-config.env', help='Configuration file path')
    parser.add_argument('--upload', help='Upload file to Google Drive')
    parser.add_argument('--remote-name', help='Remote name for uploaded file')
    parser.add_argument('--list', action='store_true', help='List backup files')
    parser.add_argument('--cleanup', type=int, help='Cleanup files older than N days')
    parser.add_argument('--storage', action='store_true', help='Show storage usage')
    parser.add_argument('--authenticate', action='store_true', help='Run authentication flow')
    
    args = parser.parse_args()
    
    # Load configuration
    config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"')
    
    # Initialize Google Drive client
    gdrive = GoogleDriveBackup(config)
    
    if not gdrive.authenticate():
        print("ERROR: Failed to authenticate with Google Drive")
        sys.exit(1)
    
    # Execute requested operation
    if args.authenticate:
        print("Authentication successful!")
    elif args.upload:
        file_id = gdrive.upload_file(args.upload, args.remote_name)
        if file_id:
            print(f"Upload successful! File ID: {file_id}")
        else:
            print("Upload failed!")
            sys.exit(1)
    elif args.list:
        files = gdrive.list_files()
        print(f"Found {len(files)} backup files:")
        for file_info in files:
            size_mb = int(file_info.get('size', 0)) / 1024 / 1024
            print(f"  {file_info['name']} ({size_mb:.1f} MB) - {file_info['createdTime']}")
    elif args.storage:
        usage = gdrive.get_storage_usage()
        if 'error' not in usage:
            total_gb = usage['total'] / 1024**3
            used_gb = usage['used'] / 1024**3
            available_gb = usage['available'] / 1024**3
            print(f"Google Drive Storage Usage:")
            print(f"  User: {usage['user_email']}")
            print(f"  Total: {total_gb:.1f} GB")
            print(f"  Used: {used_gb:.1f} GB ({used_gb/total_gb*100:.1f}%)")
            print(f"  Available: {available_gb:.1f} GB")
        else:
            print(f"Error getting storage usage: {usage['error']}")
    elif args.cleanup:
        deleted = gdrive.cleanup_old_backups(args.cleanup)
        print(f"Deleted {deleted} old backup files")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
