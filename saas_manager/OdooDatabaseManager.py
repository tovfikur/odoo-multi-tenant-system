# Standard library imports
import logging
import os
import subprocess
import xmlrpc.client

# Third-party imports
import psycopg2
import requests
from shared_utils import get_docker_client, safe_execute, log_error_with_context

class OdooDatabaseManager:
    def __init__(
        self,
        odoo_url: str,
        master_pwd: str,
        pg_host: str = "postgres",
        pg_port: int = 5432,
        pg_user: str = 'odoo_master',
        pg_password: str = None,
        backup_folder: str = './backups'
    ):
        # Odoo endpoint and master credentials
        self.odoo_url = odoo_url.rstrip('/')
        self.master_pwd = master_pwd

        # PostgreSQL connection parameters
        self.pg_host = pg_host
        self.pg_port = pg_port
        self.pg_user = pg_user
        self.pg_password = pg_password or os.getenv('POSTGRES_PASSWORD')
        if not self.pg_password:
            raise ValueError("PostgreSQL password must be supplied via pg_password or POSTGRES_PASSWORD env var")

        # Backup storage
        self.backup_folder = backup_folder
        os.makedirs(self.backup_folder, exist_ok=True)

    def is_active(self, db_name: str) -> bool:
        """
        Check if the database is active by verifying the datallowconn flag.

        Args:
            db_name (str): The name of the database to check.

        Returns:
            bool: True if the database allows connections (active), False otherwise.

        Raises:
            RuntimeError: If the database status cannot be checked.
        """
        logging.info(f"Checking active status for database: {db_name}")
        try:
            conn = psycopg2.connect(
                dbname='postgres',
                user=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT datallowconn FROM pg_database WHERE datname = %s", (db_name,))
            result = cur.fetchone()
            conn.close()
            if result is None:
                raise RuntimeError(f"Database {db_name} not found")
            is_active = result[0]
            logging.info(f"Database {db_name} is {'active' if is_active else 'inactive'}")
            return is_active
        except Exception as e:
            raise RuntimeError(f"Failed to check database status for {db_name}: {str(e)}")
        
    def backup(self, db_name: str) -> str:
        """
        Create a ZIP backup of the Odoo database.
        Returns the local path to the backup file.
        """
        logging.info(f"Backing up database: {db_name}")
        resp = requests.post(
            f"{self.odoo_url}/web/database/backup",
            data={"master_pwd": self.master_pwd, "name": db_name, "backup_format": "zip"},
            stream=True
        )
        if not resp.ok:
            raise RuntimeError(f"Backup failed: {resp.status_code} {resp.text}")

        backup_path = os.path.join(self.backup_folder, f"{db_name}.zip")
        with open(backup_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info(f"Backup saved at: {backup_path}")
        return backup_path

    def delete_backup(self, db_name: str) -> None:
        """
        Delete the backup file for the specified database from local storage.

        Args:
            db_name (str): The name of the database whose backup file should be deleted.

        Raises:
            RuntimeError: If the backup file does not exist or deletion fails.
        """
        logging.info(f"Deleting backup for database: {db_name}")
        backup_path = os.path.join(self.backup_folder, f"{db_name}.zip")
        try:
            os.remove(backup_path)
            logging.info(f"Deleted backup: {backup_path}")
        except FileNotFoundError:
            raise RuntimeError(f"Backup file not found: {backup_path}")
        except OSError as e:
            raise RuntimeError(f"Failed to delete backup file {backup_path}: {str(e)}")

    def restore(self, file_path: str, db_name: str) -> None:
        """
        Restore the database from a local ZIP backup.
        """
        logging.info(f"Restoring database: {db_name} from {file_path}")
        with open(file_path, 'rb') as f:
            files = {'backup_file': (os.path.basename(file_path), f, 'application/zip')}
            resp = requests.post(
                f"{self.odoo_url}/web/database/restore",
                data={'master_pwd': self.master_pwd, 'name': db_name, 'copy': False, 'backup_format': 'zip'},
                files=files
            )
        if not resp.ok:
            raise RuntimeError(f"Restore failed: {resp.status_code} {resp.text}")
        logging.info("Restore successful.")

    def delete(self, db_name: str) -> None:
        """
        Permanently drop the database via Odoo HTTP endpoint.
        """
        logging.info(f"Deleting database: {db_name}")
        resp = requests.post(
            f"{self.odoo_url}/web/database/drop",
            data={"master_pwd": self.master_pwd, "name": db_name}
        )
        if not resp.ok:
            raise RuntimeError(f"Delete failed: {resp.status_code} {resp.text}")
        logging.info("Database deleted.")

    def deactivate(self, db_name: str) -> None:
        """
        Deactivate cron jobs and block new connections.
        """
        logging.info(f"Deactivating database: {db_name}")
        # First disable cron jobs directly in the database
        self._update_cron_in_db(db_name, False)
        # Then block connections
        self._set_postgres_allowconn(db_name, allow=False)
        logging.info("Deactivated database.")

    def activate(self, db_name: str) -> None:
        """
        Unblock connections and activate cron jobs.
        """
        logging.info(f"Activating database: {db_name}")
        # First unblock connections
        self._set_postgres_allowconn(db_name, allow=True)
        # Then enable cron jobs
        self._update_cron_in_db(db_name, True)
        logging.info("Activated database.")

    def get_active_users_count(self, db_name: str, admin_user: str, admin_password: str, minutes: int = 30) -> int:
        """
        Get count of active users in specific Odoo database using XML-RPC API.
        Uses res.users login_date as fallback when ir.sessions is not available.
        """
        try:
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                return 0
            
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Calculate cutoff datetime
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
            
            # Try ir.sessions first (newer Odoo versions)
            try:
                session_ids = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.sessions', 'search',
                    [[['logged_at', '>=', cutoff_str], ['uid', '!=', False]]]
                )
                
                if session_ids:
                    sessions = models.execute_kw(
                        db_name, uid, admin_password,
                        'ir.sessions', 'read',
                        [session_ids, ['uid']]
                    )
                    
                    unique_users = set()
                    for session in sessions:
                        if session.get('uid'):
                            user_id = session['uid'][0] if isinstance(session['uid'], list) else session['uid']
                            unique_users.add(user_id)
                    
                    return len(unique_users)
                
                return 0
                
            except:
                # Fallback: use res.users login_date
                user_ids = models.execute_kw(
                    db_name, uid, admin_password,
                    'res.users', 'search',
                    [[['login_date', '>=', cutoff_str], ['active', '=', True]]]
                )
                
                return len(user_ids)
            
        except Exception as e:
            logging.error(f"Failed to get active users for {db_name}: {e}")
        return 0
    
    def get_installed_applications_count(self, db_name: str, admin_user: str, admin_password: str) -> int:
        """
        Get count of installed applications (not all modules) in specific Odoo database using XML-RPC API.
    
        Args:
            db_name (str): Name of the Odoo database
            admin_user (str): Admin username for authentication
            admin_password (str): Admin password for authentication
    
        Returns:
            int: Number of installed applications, 0 if connection fails
        """
        try:
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
        
            if not uid:
                print(f"[!] Authentication failed for database {db_name}")
                return 0
        
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
        
            # Search for installed applications only (not all modules)
            # Filter by: state='installed' AND application=True
            app_ids = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'search',
                [[['state', '=', 'installed'], ['application', '=', True]]]
            )
        
            app_count = len(app_ids)
            logging.info(f"Found {app_count} installed applications in database {db_name}")
            return app_count
        
        except Exception as e:
            logging.error(f"Failed to get installed applications count for {db_name}: {e}")
            return 0
        
    def get_modules_details(self, db_name: str, admin_user: str, admin_password: str) -> list:
        """
        Get detailed information about installed modules in specific Odoo database.
        
        Args:
            db_name (str): Name of the Odoo database
            admin_user (str): Admin username for authentication
            admin_password (str): Admin password for authentication
        
        Returns:
            list: List of dictionaries containing module information
        """
        try:
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                print(f"[!] Authentication failed for database {db_name}")
                return []
            
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Search for installed modules
            module_ids = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'search',
                [[['state', '=', 'installed']]]
            )
            
            if not module_ids:
                print(f"[!] No installed modules found in database {db_name}")
                return []
            
            # Get module details
            modules = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'read',
                [module_ids, ['name', 'shortdesc', 'author', 'version', 'state', 'category_id']]
            )
            
            logging.info(f"Retrieved details for {len(modules)} installed modules")
            return modules
            
        except Exception as e:
            logging.error(f"Failed to get modules details for {db_name}: {e}")
            return []

    def get_all_available_modules(self, db_name: str = None, admin_user: str = None, admin_password: str = None) -> list:
        """
        Get all available modules (both installed and uninstalled) from Odoo.
        
        Args:
            db_name (str): Name of the Odoo database (optional, uses first available if not provided)
            admin_user (str): Admin username for authentication (optional, uses default)
            admin_password (str): Admin password for authentication (optional, uses default)
        
        Returns:
            list: List of dictionaries containing all available modules information
        """
        try:
            # Use defaults if not provided
            if not db_name:
                # Try to get any available database
                db_name = "template_db"  # or use any existing tenant DB
            if not admin_user:
                admin_user = "admin"
            if not admin_password:
                admin_password = "admin"
            
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                logging.warning(f"Authentication failed for database {db_name}, trying alternative...")
                # Try with any tenant database that might exist
                return []
            
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Search for ALL modules (installed, uninstalled, etc.)
            module_ids = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'search',
                [[]]  # No filters to get all modules
            )
            
            if not module_ids:
                logging.warning(f"No modules found in database {db_name}")
                return []
            
            # Get module details (some fields might not exist in all Odoo versions)
            try:
                modules = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.module.module', 'read',
                    [module_ids, ['name', 'shortdesc', 'author', 'state', 'category_id', 'summary']]
                )
            except:
                # Fallback with minimal fields if some don't exist
                modules = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.module.module', 'read',
                    [module_ids, ['name', 'shortdesc', 'state', 'category_id']]
                )
            
            # Filter and format modules
            formatted_modules = []
            for module in modules:
                # Only skip truly core technical modules that shouldn't be user-selectable
                skip_modules = ['base', 'web']
                if module['name'] in skip_modules:
                    continue
                    
                # Skip modules without a proper name or description
                if not module.get('name') or module['name'].startswith('test_'):
                    continue
                    
                # Handle shortdesc which might be JSON format like {"en_US": "Sales"}
                display_name = module['name']
                if module.get('shortdesc'):
                    if isinstance(module['shortdesc'], dict):
                        # Extract English version if available
                        display_name = module['shortdesc'].get('en_US', module['shortdesc'].get('en', module['name']))
                    else:
                        display_name = module['shortdesc']
                
                formatted_modules.append({
                    'name': module['name'],
                    'display_name': display_name,
                    'description': module.get('summary', ''),
                    'state': module['state'],
                    'category': module['category_id'][1] if module['category_id'] else 'Other',
                    'author': module.get('author', ''),
                    'version': ''  # Version field might not be available
                })
            
            logging.info(f"Retrieved {len(formatted_modules)} available modules")
            return formatted_modules
            
        except Exception as e:
            logging.error(f"Failed to get available modules: {e}")
            return []

    def get_modules_by_category(self, db_name: str, admin_user: str, admin_password: str) -> dict:
        """
        Get installed modules grouped by category.
        
        Args:
            db_name (str): Name of the Odoo database
            admin_user (str): Admin username for authentication
            admin_password (str): Admin password for authentication
        
        Returns:
            dict: Dictionary with categories as keys and module lists as values
        """
        try:
            modules = self.get_modules_details(db_name, admin_user, admin_password)
            
            if not modules:
                return {}
            
            categorized = {}
            for module in modules:
                category = 'Uncategorized'
                if module.get('category_id') and isinstance(module['category_id'], list):
                    category = module['category_id'][1]  # category_id is [id, name]
                
                if category not in categorized:
                    categorized[category] = []
                
                categorized[category].append({
                    'name': module.get('name', 'Unknown'),
                    'description': module.get('shortdesc', 'No description'),
                    'author': module.get('author', 'Unknown'),
                    'version': module.get('version', 'Unknown')
                })
            
            # Log summary
            logging.info(f"Modules grouped into {len(categorized)} categories:")
            for category, modules_list in categorized.items():
                logging.info(f"    - {category}: {len(modules_list)} modules")
            
            return categorized
            
        except Exception as e:
            logging.error(f"Failed to categorize modules for {db_name}: {e}")
            return {}


    def get_available_applications(self, db_name: str, admin_user: str, admin_password: str) -> list:
        """
        Get list of available applications (not installed) in specific Odoo database using XML-RPC API.
        Outputs a formatted table with tenant name and application information including icon path.
        
        Args:
            db_name (str): Name of the Odoo database
            admin_user (str): Admin username for authentication
            admin_password (str): Admin password for authentication
        
        Returns:
            list: List of dictionaries containing available application information
        """
        try:
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                print(f"[!] Authentication failed for database {db_name}")
                return []
            
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Search for available applications (not installed, installable, and marked as application)
            app_ids = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'search',
                [[['state', '=', 'uninstalled'], ['application', '=', True]]]
            )
            
            if not app_ids:
                print(f"[!] No available applications found in database {db_name}")
                return []
            
            # Define fields to fetch, excluding 'version' if it might not exist
            fields = ['name', 'shortdesc', 'author', 'category_id', 'website', 'state', 'icon']
            try:
                # Check if 'version' field exists
                fields_info = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.module.module', 'fields_get',
                    [[]], {'attributes': ['string', 'type']}
                )
                if 'version' in fields_info:
                    fields.append('version')
            except Exception as e:
                print(f"[!] Could not verify 'version' field existence: {e}")
            
            # Get application details
            apps = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'read',
                [app_ids, fields]
            )
            
            formatted_apps = []
            table_data = []
            for app in apps:
                category = app.get('category_id', [None, 'Uncategorized'])[1]
                # Debug: Log raw icon field value
                print(f"Debug: Icon field for {app.get('name', 'Unknown')}: {app.get('icon')}")
                # Use module's static/description/icon.png path
                icon_path = f"/{app.get('name', 'unknown')}/static/description/icon.png"
                app_info = {
                    'name': app.get('name', 'Unknown'),
                    'technical_name': app.get('name', 'Unknown'),
                    'summary': app.get('shortdesc', ''),
                    'version': app.get('version', 'Unknown') if 'version' in app else 'Unknown',
                    'category': category,
                    'website': app.get('website', ''),
                    'state': app.get('state', 'uninstalled'),
                    'icon': icon_path
                }
                formatted_apps.append(app_info)
                table_data.append([
                    db_name,
                    'Available',
                    app_info['name'],
                    app_info['technical_name'],
                    app_info['summary'],
                    app_info['version'],
                    app_info['category'],
                    app_info['website'],
                    app_info['icon']
                ])
            
            # Print formatted table
            headers = ['Tenant', 'Status', 'Name', 'Technical Name', 'Summary', 'Version', 'Category', 'Website', 'Icon Path']
            try:
                print(f"\n[✓] Available Applications for {db_name}:")
                print(tabulate(table_data, headers=headers, tablefmt='grid', stralign='left', maxcolwidths=[None, None, 20, 20, 30, None, 20, 30, 60]))
                print(f"[✓] Retrieved {len(formatted_apps)} available applications for {db_name}")
            except ImportError:
                print(f"[!] 'tabulate' library not installed. Falling back to simple output.")
                print(f"[✓] Available Applications for {db_name}:")
                for app in formatted_apps:
                    print(f"  - Tenant: {db_name}, Status: Available, Name: {app['name']}, "
                        f"Technical Name: {app['technical_name']}, Summary: {app['summary']}, "
                        f"Version: {app['version']}, Category: {app['category']}, "
                        f"Website: {app['website']}, Icon: {app['icon']}")
                print(f"[✓] Retrieved {len(formatted_apps)} available applications for {db_name}")
            
            return formatted_apps
            
        except Exception as e:
            print(f"[!] Failed to get available applications for {db_name}: {e}")
            return []

    def get_installed_applications(self, db_name: str, admin_user: str, admin_password: str) -> list:
        """
        Get list of installed applications in specific Odoo database using XML-RPC API.
        Outputs a formatted table with tenant name and application information including icon path.
        
        Args:
            db_name (str): Name of the Odoo database
            admin_user (str): Admin username for authentication
            admin_password (str): Admin password for authentication
        
        Returns:
            list: List of dictionaries containing installed application information
        """
        try:
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                print(f"[!] Authentication failed for database {db_name}")
                return []
            
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Search for installed applications
            app_ids = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'search',
                [[['state', '=', 'installed'], ['application', '=', True]]]
            )
            
            if not app_ids:
                print(f"[!] No installed applications found in database {db_name}")
                return []
            
            # Define fields to fetch, excluding problematic fields if they don't exist
            fields = ['name', 'shortdesc', 'author', 'category_id', 'website', 'state', 'icon']
            try:
                # Check available fields in ir.module.module
                fields_info = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.module.module', 'fields_get',
                    [[]], {'attributes': ['string', 'type']}
                )
                if 'version' in fields_info:
                    fields.append('version')
                if 'install_date' in fields_info:
                    fields.append('install_date')
            except Exception as e:
                print(f"[!] Could not verify field existence: {e}")
            
            # Get application details
            apps = models.execute_kw(
                db_name, uid, admin_password,
                'ir.module.module', 'read',
                [app_ids, fields]
            )
            
            formatted_apps = []
            table_data = []
            for app in apps:
                category = app.get('category_id', [None, 'Uncategorized'])[1]
                # Debug: Log raw icon field value
                print(f"Debug: Icon field for {app.get('name', 'Unknown')}: {app.get('icon')}")
                # Use module's static/description/icon.png path
                icon_path = f"/{app.get('name', 'unknown')}/static/description/icon.png"
                app_info = {
                    'name': app.get('name', 'Unknown'),
                    'technical_name': app.get('name', 'Unknown'),
                    'summary': app.get('shortdesc', ''),
                    'version': app.get('version', 'Unknown') if 'version' in app else 'Unknown',
                    'category': category,
                    'website': app.get('website', ''),
                    'state': app.get('state', 'installed'),
                    'install_date': app.get('install_date', None) if 'install_date' in app else None,
                    'icon': icon_path
                }
                formatted_apps.append(app_info)
                table_data.append([
                    db_name,
                    'Installed',
                    app_info['name'],
                    app_info['technical_name'],
                    app_info['summary'],
                    app_info['version'],
                    app_info['category'],
                    app_info['website'],
                    app_info['icon']
                ])
            
            # Print formatted table
            headers = ['Tenant', 'Status', 'Name', 'Technical Name', 'Summary', 'Version', 'Category', 'Website', 'Icon Path']
            try:
                print(f"\n[✓] Installed Applications for {db_name}:")
                print(tabulate(table_data, headers=headers, tablefmt='grid', stralign='left', maxcolwidths=[None, None, 20, 20, 30, None, 20, 30, 60]))
                print(f"[✓] Retrieved {len(formatted_apps)} installed applications for {db_name}")
            except ImportError:
                print(f"[!] 'tabulate' library not installed. Falling back to simple output.")
                print(f"[✓] Installed Applications for {db_name}:")
                for app in formatted_apps:
                    print(f"  - Tenant: {db_name}, Status: Installed, Name: {app['name']}, "
                        f"Technical Name: {app['technical_name']}, Summary: {app['summary']}, "
                        f"Version: {app['version']}, Category: {app['category']}, "
                        f"Website: {app['website']}, Icon: {app['icon']}")
                print(f"[✓] Retrieved {len(formatted_apps)} installed applications for {db_name}")
            
            return formatted_apps
            
        except Exception as e:
            print(f"[!] Failed to get installed applications for {db_name}: {e}")
            return []


    def _get_postgres_container_name(self) -> str:
        """Get the actual PostgreSQL container name."""
        try:
            # Try common patterns for container names
            possible_names = [
                'postgres',
                f'{self._get_project_name()}_postgres_1',
                f'{self._get_project_name()}-postgres-1',
                f'{self._get_project_name()}_postgres',
                f'{self._get_project_name()}-postgres'
            ]
            
            for name in possible_names:
                cmd = ['docker', 'ps', '--filter', f'name={name}', '--format', '{{.Names}}']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0 and result.stdout.strip():
                    container_name = result.stdout.strip().split('\n')[0]
                    print(f"[✓] Found PostgreSQL container: {container_name}")
                    return container_name
            
            # Fallback: find by image
            cmd = ['docker', 'ps', '--filter', 'ancestor=postgres:15', '--format', '{{.Names}}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                container_name = result.stdout.strip().split('\n')[0]
                print(f"[✓] Found PostgreSQL container by image: {container_name}")
                return container_name
                
            raise RuntimeError("PostgreSQL container not found")
            
        except Exception as e:
            print(f"[!] Error finding PostgreSQL container: {e}")
            raise

    def _get_odoo_container_name(self) -> str:
        """Get an Odoo container name that has access to filestore."""
        try:
            # Try to find odoo_master container first
            possible_names = [
                'odoo_master',
                f'{self._get_project_name()}_odoo_master_1',
                f'{self._get_project_name()}-odoo_master-1',
                f'{self._get_project_name()}_odoo_master',
                f'{self._get_project_name()}-odoo_master'
            ]
            
            for name in possible_names:
                cmd = ['docker', 'ps', '--filter', f'name={name}', '--format', '{{.Names}}']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0 and result.stdout.strip():
                    container_name = result.stdout.strip().split('\n')[0]
                    print(f"[✓] Found Odoo container: {container_name}")
                    return container_name
            
            # Fallback: find any odoo container
            cmd = ['docker', 'ps', '--filter', 'ancestor=odoo:17.0', '--format', '{{.Names}}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                container_name = result.stdout.strip().split('\n')[0]
                print(f"[✓] Found Odoo container by image: {container_name}")
                return container_name
                
            raise RuntimeError("Odoo container not found")
            
        except Exception as e:
            print(f"[!] Error finding Odoo container: {e}")
            raise

    def _get_redis_container_name(self) -> str:
        """Get the Redis container name."""
        try:
            possible_names = [
                'redis',
                f'{self._get_project_name()}_redis_1',
                f'{self._get_project_name()}-redis-1',
                f'{self._get_project_name()}_redis',
                f'{self._get_project_name()}-redis'
            ]
            
            for name in possible_names:
                cmd = ['docker', 'ps', '--filter', f'name={name}', '--format', '{{.Names}}']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0 and result.stdout.strip():
                    container_name = result.stdout.strip().split('\n')[0]
                    print(f"[✓] Found Redis container: {container_name}")
                    return container_name
            
            # Fallback: find by image
            cmd = ['docker', 'ps', '--filter', 'ancestor=redis:7-alpine', '--format', '{{.Names}}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                container_name = result.stdout.strip().split('\n')[0]
                print(f"[✓] Found Redis container by image: {container_name}")
                return container_name
                
            return ''  # Redis is optional
            
        except Exception as e:
            print(f"[!] Error finding Redis container: {e}")
            return ''

    def _get_project_name(self) -> str:
        """Get Docker Compose project name from current directory."""
        try:
            # Get project name from docker-compose
            cmd = ['docker', 'compose', 'config', '--format', 'json']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                config = json.loads(result.stdout)
                if 'name' in config:
                    return config['name']
            
            # Fallback: use current directory name (common default)
            return os.path.basename(os.getcwd()).lower()
            
        except Exception:
            return os.path.basename(os.getcwd()).lower()

    def _get_postgres_size_from_container(self, db_name: str) -> int:
        """Get PostgreSQL database size by executing command in postgres container."""
        try:
            postgres_container = self._get_postgres_container_name()
            
            # Execute pg_database_size query inside postgres container
            cmd = [
                'docker', 'exec', postgres_container,
                'psql', 
                '-U', self.pg_user,
                '-d', 'postgres',
                '-t', '-c', f"SELECT pg_database_size('{db_name}');"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                size_str = result.stdout.strip()
                if size_str and size_str.isdigit():
                    size_bytes = int(size_str)
                    print(f"[✓] PostgreSQL database size: {self._bytes_to_human(size_bytes)}")
                    return size_bytes
                else:
                    print(f"[!] Invalid database size response: '{size_str}'")
            else:
                print(f"[!] Failed to get database size from container: {result.stderr}")
            
            return 0
            
        except Exception as e:
            print(f"[!] Error getting PostgreSQL size from container: {e}")
            return 0

    def _get_docker_filestore_size(self, db_name: str) -> tuple:
        """Get file attachments size from Docker volume."""
        try:
            odoo_container = self._get_odoo_container_name()
            
            # Try different common filestore paths
            filestore_paths = [
                f'/var/lib/odoo/filestore/{db_name}',
                f'/opt/odoo/filestore/{db_name}',
                f'/var/lib/odoo/{db_name}/filestore'
            ]
            
            for path in filestore_paths:
                cmd = ['docker', 'exec', odoo_container, 'du', '-sb', path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    size_str = result.stdout.split()[0]
                    if size_str.isdigit():
                        size_bytes = int(size_str)
                        print(f"[✓] File attachments size: {self._bytes_to_human(size_bytes)} (container:{path})")
                        return size_bytes, path
            
            # If no filestore found, check if directory exists but is empty
            for path in filestore_paths:
                cmd = ['docker', 'exec', odoo_container, 'test', '-d', path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    print(f"[✓] Filestore directory exists but is empty: {path}")
                    return 0, path
            
            print(f"[!] Filestore directory not found for database {db_name}")
            return 0, ''
            
        except Exception as e:
            print(f"[!] Error getting filestore size: {e}")
            return 0, ''

    def _get_redis_cache_size(self, db_name: str) -> int:
        """Get Redis cache usage for specific database."""
        try:
            redis_container = self._get_redis_container_name()
            if not redis_container:
                print("[!] Redis container not found, skipping cache calculation")
                return 0
            
            # Get memory usage from Redis container
            cmd = ['docker', 'exec', redis_container, 'redis-cli', 'INFO', 'memory']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                memory_info = result.stdout
                for line in memory_info.split('\n'):
                    if line.startswith('used_memory:'):
                        total_redis_memory = int(line.split(':')[1])
                        
                        # Estimate database-specific usage (rough approximation)
                        cmd_keys = ['docker', 'exec', redis_container, 'redis-cli', 'EVAL', 
                                f'return #redis.call("keys", "{db_name}*")', '0']
                        
                        keys_result = subprocess.run(cmd_keys, capture_output=True, text=True, timeout=10)
                        if keys_result.returncode == 0 and keys_result.stdout.strip().isdigit():
                            db_keys = int(keys_result.stdout.strip())
                            
                            # Get total keys
                            cmd_total = ['docker', 'exec', redis_container, 'redis-cli', 'DBSIZE']
                            total_result = subprocess.run(cmd_total, capture_output=True, text=True, timeout=10)
                            
                            if total_result.returncode == 0 and total_result.stdout.strip().isdigit():
                                total_keys = int(total_result.stdout.strip())
                                
                                if total_keys > 0:
                                    estimated_db_memory = int((db_keys / total_keys) * total_redis_memory)
                                    print(f"[✓] Estimated Redis cache for {db_name}: {self._bytes_to_human(estimated_db_memory)}")
                                    return estimated_db_memory
                        
                        return 0
            
            return 0
            
        except Exception as e:
            print(f"[!] Error getting Redis cache size: {e}")
            return 0

    def get_database_storage_usage(self, db_name: str, include_docker_volumes: bool = True) -> dict:
        """
        Calculate total storage usage for a specific Odoo database in Docker environment including:
        - Database size in PostgreSQL container
        - File attachments in shared odoo_filestore volume
        - Redis cache usage (if applicable)
        - Docker volume overhead
        
        Args:
            db_name (str): Name of the Odoo database
            include_docker_volumes (bool): Include Docker volume size calculations
        
        Returns:
            dict: Storage usage breakdown in bytes and human-readable format
        """
        try:
            storage_info = {
                'database_size_bytes': 0,
                'attachments_size_bytes': 0,
                'redis_cache_bytes': 0,
                'docker_volume_overhead_bytes': 0,
                'total_size_bytes': 0,
                'database_size_human': '0 B',
                'attachments_size_human': '0 B',
                'redis_cache_human': '0 B',
                'docker_volume_overhead_human': '0 B',
                'total_size_human': '0 B',
                'filestore_path': '',
                'calculation_method': 'docker'
            }
            
            print(f"[+] Calculating Docker-based storage usage for database: {db_name}")
            
            # 1. Get PostgreSQL database size from postgres container
            storage_info['database_size_bytes'] = self._get_postgres_size_from_container(db_name)
            
            # 2. Get file attachments size from Docker volume
            storage_info['attachments_size_bytes'], storage_info['filestore_path'] = self._get_docker_filestore_size(db_name)
            
            # 3. Get Redis cache usage for this database (if applicable)
            storage_info['redis_cache_bytes'] = self._get_redis_cache_size(db_name)
            
            # 4. Get Docker volume overhead (if requested)
            if include_docker_volumes:
                storage_info['docker_volume_overhead_bytes'] = self._get_docker_volume_overhead(db_name)
            
            # 5. Calculate total
            storage_info['total_size_bytes'] = (
                storage_info['database_size_bytes'] + 
                storage_info['attachments_size_bytes'] + 
                storage_info['redis_cache_bytes'] +
                storage_info['docker_volume_overhead_bytes']
            )
            
            # 6. Convert to human-readable format
            storage_info['database_size_human'] = self._bytes_to_human(storage_info['database_size_bytes'])
            storage_info['attachments_size_human'] = self._bytes_to_human(storage_info['attachments_size_bytes'])
            storage_info['redis_cache_human'] = self._bytes_to_human(storage_info['redis_cache_bytes'])
            storage_info['docker_volume_overhead_human'] = self._bytes_to_human(storage_info['docker_volume_overhead_bytes'])
            storage_info['total_size_human'] = self._bytes_to_human(storage_info['total_size_bytes'])
            
            # Print detailed summary
            self._print_storage_summary(db_name, storage_info)
            
            return storage_info
            
        except Exception as e:
            print(f"[!] Failed to calculate storage usage for {db_name}: {e}")
            return storage_info

    def _get_docker_volume_overhead(self, db_name: str) -> int:
        """Calculate Docker volume overhead for this database."""
        try:
            # Get volume information using Docker API
            client = get_docker_client()
            
            # Get odoo_filestore volume info
            try:
                volume = client.volumes.get('odoo_filestore')
                # This is a rough estimate of metadata overhead
                return 1024 * 1024  # 1MB estimate for volume metadata
            except:
                return 0
                
        except Exception as e:
            print(f"[!] Error calculating Docker volume overhead: {e}")
            return 0

    def _print_storage_summary(self, db_name: str, storage_info: dict):
        """Print formatted storage summary."""
        print(f"\n[✓] 🐳 Docker Storage Summary for '{db_name}':")
        print("=" * 70)
        print(f"    📊 Database (PostgreSQL):     {storage_info['database_size_human']:>12}")
        print(f"    📁 File Attachments:          {storage_info['attachments_size_human']:>12}")
        print(f"    🗂️  Redis Cache (estimated):   {storage_info['redis_cache_human']:>12}")
        print(f"    🐳 Docker Volume Overhead:    {storage_info['docker_volume_overhead_human']:>12}")
        print("=" * 70)
        print(f"    🔢 TOTAL STORAGE USAGE:       {storage_info['total_size_human']:>12}")
        print("=" * 70)
        
        if storage_info['filestore_path']:
            print(f"    📂 Filestore Path: {storage_info['filestore_path']}")

    def _bytes_to_human(self, bytes_size: int) -> str:
        """Convert bytes to human readable format."""
        if bytes_size == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                if unit == 'B':
                    return f"{int(bytes_size)} {unit}"
                else:
                    return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        
        return f"{bytes_size:.2f} PB"

    def get_all_tenant_storage_summary(self) -> dict:
        """Get storage summary for all tenant databases in the Docker environment."""
        try:
            postgres_container = self._get_postgres_container_name()
            
            # Get list of all databases from postgres container
            cmd = [
                'docker', 'exec', postgres_container,
                'psql', '-U', self.pg_user, '-d', 'postgres',
                '-t', '-c', 
                "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres', 'odoo_master');"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"[!] Failed to get database list: {result.stderr}")
                return {}
            
            databases = [db.strip() for db in result.stdout.strip().split('\n') if db.strip()]
            
            total_storage = 0
            db_summary = {}
            
            print(f"[+] 🐳 Calculating Docker storage for {len(databases)} tenant databases...")
            print("=" * 100)
            
            for db_name in databases:
                if db_name:  # Skip empty lines
                    storage_info = self.get_database_storage_usage(db_name)
                    db_summary[db_name] = storage_info
                    total_storage += storage_info['total_size_bytes']
                    print("-" * 100)
            
            print(f"\n🎯 TOTAL STORAGE ACROSS ALL TENANTS: {self._bytes_to_human(total_storage)}")
            
            return {
                'databases': db_summary,
                'total_storage_bytes': total_storage,
                'total_storage_human': self._bytes_to_human(total_storage),
                'database_count': len(databases),
                'environment': 'docker'
            }
            
        except Exception as e:
            print(f"[!] Failed to get tenant storage summary: {e}")
            return {}



    def get_tenant_uptime(self, db_name: str, admin_user: str = None, admin_password: str = None) -> dict:
        """
        Calculate uptime for a tenant database using multiple methods:
        1. PostgreSQL stats_collector start time (most accurate for DB uptime)
        2. Odoo server start time via XML-RPC (if credentials provided)
        3. Database activation timestamp (if tracked)
        
        Args:
            db_name (str): Name of the tenant database
            admin_user (str, optional): Admin username for XML-RPC authentication
            admin_password (str, optional): Admin password for XML-RPC authentication
        
        Returns:
            dict: Uptime information including seconds, human-readable format, and calculation method
        """
        from datetime import datetime, timedelta, timezone
        import time
        
        uptime_info = {
            'database_name': db_name,
            'uptime_seconds': 0,
            'uptime_human': '0 seconds',
            'uptime_days': 0,
            'uptime_hours': 0,
            'uptime_minutes': 0,
            'start_time': None,
            'current_time': datetime.now().isoformat(),
            'calculation_method': 'unknown',
            'is_active': False,
            'error': None
        }
        
        try:
            # First check if database is active
            uptime_info['is_active'] = self.is_active(db_name)
            
            if not uptime_info['is_active']:
                uptime_info['error'] = 'Database is not active'
                print(f"[!] Database {db_name} is not active, uptime calculation skipped")
                return uptime_info
            
            print(f"[+] Calculating uptime for tenant database: {db_name}")
            
            # Method 1: Try PostgreSQL stats_collector start time (most reliable)
            pg_uptime = self._get_postgres_uptime(db_name)
            if pg_uptime:
                uptime_info.update(pg_uptime)
                uptime_info['calculation_method'] = 'postgresql_stats'
                print(f"[✓] PostgreSQL uptime calculated: {uptime_info['uptime_human']}")
                return uptime_info
            
            # Method 2: Try Odoo server uptime via XML-RPC (if credentials provided)
            if admin_user and admin_password:
                odoo_uptime = self._get_odoo_server_uptime(db_name, admin_user, admin_password)
                if odoo_uptime:
                    uptime_info.update(odoo_uptime)
                    uptime_info['calculation_method'] = 'odoo_xmlrpc'
                    print(f"[✓] Odoo server uptime calculated: {uptime_info['uptime_human']}")
                    return uptime_info
            
            # Method 3: Try Docker container uptime
            container_uptime = self._get_container_uptime()
            if container_uptime:
                uptime_info.update(container_uptime)
                uptime_info['calculation_method'] = 'docker_container'
                print(f"[✓] Docker container uptime calculated: {uptime_info['uptime_human']}")
                return uptime_info
            
            # Method 4: Fallback to PostgreSQL backend start time
            backend_uptime = self._get_postgres_backend_uptime(db_name)
            if backend_uptime:
                uptime_info.update(backend_uptime)
                uptime_info['calculation_method'] = 'postgresql_backend'
                print(f"[✓] PostgreSQL backend uptime calculated: {uptime_info['uptime_human']}")
                return uptime_info
            
            uptime_info['error'] = 'Unable to determine uptime using any available method'
            print(f"[!] Could not calculate uptime for {db_name}")
            
        except Exception as e:
            uptime_info['error'] = str(e)
            print(f"[!] Error calculating uptime for {db_name}: {e}")
        
        return uptime_info

    def _get_postgres_uptime(self, db_name: str) -> dict:
        """Get PostgreSQL database uptime from stats_collector."""
        from datetime import datetime, timezone
        
        try:
            conn = psycopg2.connect(
                dbname='postgres',
                user=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port
            )
            cur = conn.cursor()
            
            # Get PostgreSQL server start time
            cur.execute("SELECT pg_postmaster_start_time();")
            result = cur.fetchone()
            conn.close()
            
            if result and result[0]:
                start_time = result[0]
                # Handle timezone aware datetime
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                uptime_seconds = int((current_time - start_time).total_seconds())
                
                return {
                    'uptime_seconds': uptime_seconds,
                    'uptime_human': self._seconds_to_human(uptime_seconds),
                    'uptime_days': uptime_seconds // 86400,
                    'uptime_hours': (uptime_seconds % 86400) // 3600,
                    'uptime_minutes': (uptime_seconds % 3600) // 60,
                    'start_time': start_time.isoformat()
                }
        except Exception as e:
            print(f"[!] Failed to get PostgreSQL uptime: {e}")
        
        return None

    def _get_odoo_server_uptime(self, db_name: str, admin_user: str, admin_password: str) -> dict:
        """Get Odoo server uptime via XML-RPC."""
        from datetime import datetime, timezone
        
        try:
            import xmlrpc.client
            
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                return None
            
            # Get server info
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Try to get server start time from ir.config_parameter or system info
            try:
                # Method 1: Check if there's a server_start_time parameter
                start_time_param = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.config_parameter', 'search_read',
                    [[['key', '=', 'server_start_time']]],
                    {'fields': ['value']}
                )
                
                if start_time_param:
                    start_time_str = start_time_param[0]['value']
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    current_time = datetime.now(timezone.utc)
                    uptime_seconds = int((current_time - start_time).total_seconds())
                    
                    return {
                        'uptime_seconds': uptime_seconds,
                        'uptime_human': self._seconds_to_human(uptime_seconds),
                        'uptime_days': uptime_seconds // 86400,
                        'uptime_hours': (uptime_seconds % 86400) // 3600,
                        'uptime_minutes': (uptime_seconds % 3600) // 60,
                        'start_time': start_time.isoformat()
                    }
            except:
                pass
            
            # Method 2: Use oldest active session as approximation
            try:
                session_ids = models.execute_kw(
                    db_name, uid, admin_password,
                    'ir.sessions', 'search',
                    [[['uid', '!=', False]]],
                    {'order': 'logged_at asc', 'limit': 1}
                )
                
                if session_ids:
                    session = models.execute_kw(
                        db_name, uid, admin_password,
                        'ir.sessions', 'read',
                        [session_ids[0], ['logged_at']]
                    )
                    
                    if session and session[0].get('logged_at'):
                        start_time = datetime.fromisoformat(session[0]['logged_at'].replace('Z', '+00:00'))
                        current_time = datetime.now(timezone.utc)
                        uptime_seconds = int((current_time - start_time).total_seconds())
                        
                        return {
                            'uptime_seconds': uptime_seconds,
                            'uptime_human': self._seconds_to_human(uptime_seconds),
                            'uptime_days': uptime_seconds // 86400,
                            'uptime_hours': (uptime_seconds % 86400) // 3600,
                            'uptime_minutes': (uptime_seconds % 3600) // 60,
                            'start_time': start_time.isoformat()
                        }
            except:
                pass
                
        except Exception as e:
            print(f"[!] Failed to get Odoo server uptime: {e}")
        
        return None

    def _get_container_uptime(self) -> dict:
        """Get Docker container uptime."""
        from datetime import datetime, timezone
        
        try:
            # Get Odoo container uptime
            odoo_container = self._get_odoo_container_name()
            
            cmd = ['docker', 'inspect', odoo_container, '--format', '{{.State.StartedAt}}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                start_time_str = result.stdout.strip()
                # Parse Docker's timestamp format
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                uptime_seconds = int((current_time - start_time).total_seconds())
                
                return {
                    'uptime_seconds': uptime_seconds,
                    'uptime_human': self._seconds_to_human(uptime_seconds),
                    'uptime_days': uptime_seconds // 86400,
                    'uptime_hours': (uptime_seconds % 86400) // 3600,
                    'uptime_minutes': (uptime_seconds % 3600) // 60,
                    'start_time': start_time.isoformat()
                }
                
        except Exception as e:
            print(f"[!] Failed to get container uptime: {e}")
        
        return None

    def _get_postgres_backend_uptime(self, db_name: str) -> dict:
        """Get uptime from PostgreSQL backend start time for specific database."""
        from datetime import datetime, timezone
        
        try:
            conn = psycopg2.connect(
                dbname='postgres',
                user=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port
            )
            cur = conn.cursor()
            
            # Get oldest backend start time for this database
            cur.execute("""
                SELECT MIN(backend_start) 
                FROM pg_stat_activity 
                WHERE datname = %s AND state = 'active'
            """, (db_name,))
            
            result = cur.fetchone()
            conn.close()
            
            if result and result[0]:
                start_time = result[0]
                # Handle timezone aware datetime
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                uptime_seconds = int((current_time - start_time).total_seconds())
                
                return {
                    'uptime_seconds': uptime_seconds,
                    'uptime_human': self._seconds_to_human(uptime_seconds),
                    'uptime_days': uptime_seconds // 86400,
                    'uptime_hours': (uptime_seconds % 86400) // 3600,
                    'uptime_minutes': (uptime_seconds % 3600) // 60,
                    'start_time': start_time.isoformat()
                }
                
        except Exception as e:
            print(f"[!] Failed to get PostgreSQL backend uptime: {e}")
        
        return None

    def _seconds_to_human(self, seconds: int) -> str:
        """Convert seconds to human-readable uptime format."""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes} minutes, {secs} seconds"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours} hours, {minutes} minutes"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            minutes = (seconds % 3600) // 60
            return f"{days} days, {hours} hours, {minutes} minutes"

    def get_all_tenants_uptime(self) -> dict:
        """Get uptime summary for all active tenant databases."""
        from datetime import datetime
        
        try:
            postgres_container = self._get_postgres_container_name()
            
            # Get list of all active databases
            cmd = [
                'docker', 'exec', postgres_container,
                'psql', '-U', self.pg_user, '-d', 'postgres',
                '-t', '-c', 
                """SELECT datname FROM pg_database 
                WHERE datistemplate = false 
                AND datname NOT IN ('postgres', 'odoo_master')
                AND datallowconn = true;"""
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"[!] Failed to get active database list: {result.stderr}")
                return {}
            
            databases = [db.strip() for db in result.stdout.strip().split('\n') if db.strip()]
            
            uptime_summary = {}
            total_uptime = 0
            active_count = 0
            
            print(f"[+] Calculating uptime for {len(databases)} active tenant databases...")
            print("=" * 100)
            
            for db_name in databases:
                if db_name:
                    uptime_info = self.get_tenant_uptime(db_name)
                    uptime_summary[db_name] = uptime_info
                    
                    if uptime_info['is_active'] and uptime_info['uptime_seconds'] > 0:
                        total_uptime += uptime_info['uptime_seconds']
                        active_count += 1
                    
                    print(f"[✓] {db_name}: {uptime_info['uptime_human']} ({uptime_info['calculation_method']})")
                    print("-" * 100)
            
            average_uptime = total_uptime // active_count if active_count > 0 else 0
            
            return {
                'databases': uptime_summary,
                'total_databases': len(databases),
                'active_databases': active_count,
                'average_uptime_seconds': average_uptime,
                'average_uptime_human': self._seconds_to_human(average_uptime),
                'calculation_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"[!] Failed to get tenant uptime summary: {e}")
            return {}


    def get_users_count(self, db_name: str, admin_user: str, admin_password: str, include_inactive: bool = False) -> dict:
        """
        Get count of users in specific Odoo database using XML-RPC API.
        
        Args:
            db_name (str): Name of the Odoo database
            admin_user (str): Admin username for authentication
            admin_password (str): Admin password for authentication
            include_inactive (bool): Whether to include inactive users in count
        
        Returns:
            dict: Dictionary containing user counts and breakdown
        """
        try:
            # Authenticate
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
            uid = common.authenticate(db_name, admin_user, admin_password, {})
            
            if not uid:
                print(f"[!] Authentication failed for database {db_name}")
                return {'total_users': 0, 'active_users': 0, 'inactive_users': 0, 'error': 'Authentication failed'}
            
            # Connect to object endpoint
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
            
            # Get all users (excluding system users)
            domain = [['id', '!=', 1]]  # Exclude admin user (id=1)
            if not include_inactive:
                domain.append(['active', '=', True])
            
            # Count total users
            total_user_ids = models.execute_kw(
                db_name, uid, admin_password,
                'res.users', 'search',
                [domain]
            )
            
            # Count active users specifically
            active_user_ids = models.execute_kw(
                db_name, uid, admin_password,
                'res.users', 'search',
                [[['id', '!=', 1], ['active', '=', True]]]
            )
            
            # Count inactive users
            inactive_user_ids = models.execute_kw(
                db_name, uid, admin_password,
                'res.users', 'search',
                [[['id', '!=', 1], ['active', '=', False]]]
            )
            
            # Get user details for additional info
            if total_user_ids:
                users_info = models.execute_kw(
                    db_name, uid, admin_password,
                    'res.users', 'read',
                    [total_user_ids[:5], ['name', 'login', 'active', 'create_date']]  # Get first 5 as sample
                )
            else:
                users_info = []
            
            result = {
                'total_users': len(total_user_ids),
                'active_users': len(active_user_ids),
                'inactive_users': len(inactive_user_ids),
                'sample_users': users_info,
                'database_name': db_name,
                'error': None
            }
            
            print(f"[✓] User count for {db_name}:")
            print(f"    - Total users: {result['total_users']}")
            print(f"    - Active users: {result['active_users']}")
            print(f"    - Inactive users: {result['inactive_users']}")
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to get user count for {db_name}: {str(e)}"
            print(f"[!] {error_msg}")
            return {
                'total_users': 0,
                'active_users': 0,
                'inactive_users': 0,
                'sample_users': [],
                'database_name': db_name,
                'error': error_msg
            }


    def _update_cron_in_db(self, db_name: str, active: bool) -> None:
        """
        Connect directly to the tenant database and update ir_cron.active.
        """
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("UPDATE ir_cron SET active = %s", (active,))
            conn.close()
            state = 'enabled' if active else 'disabled'
            print(f"[✓] Cron jobs {state} in PostgreSQL.")
        except Exception as e:
            print(f"[!] Failed to update cron in DB: {e}")

    def _set_postgres_allowconn(self, db_name: str, allow: bool) -> None:
        """
        Toggle datallowconn flag and optionally terminate sessions.
        """
        try:
            conn = psycopg2.connect(
                dbname='postgres',
                user=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("UPDATE pg_database SET datallowconn = %s WHERE datname = %s", (allow, db_name))
            if not allow:
                cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (db_name,))
            conn.close()
            state = 'unblocked' if allow else 'blocked'
            print(f"[✓] PostgreSQL connections {state}.")
        except Exception as e:
            print(f"[!] PostgreSQL error: {e}")

    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
