import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

class SecretManager:
    def __init__(self, key_path='.secret.key'):
        self.key_path = key_path
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                self.key = f.read()
        else:
            self.key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(self.key)
        self.cipher = Fernet(self.key)
    
    def get_secret(self, name: str):
        # Prioritas 1: Environment Variable
        val = os.getenv(name)
        if val:
            return val
        
        # Prioritas 2: File terenkripsi
        encrypted_path = f".secrets/{name}.enc"
        if os.path.exists(encrypted_path):
            with open(encrypted_path, 'rb') as f:
                encrypted_data = f.read()
            return self.cipher.decrypt(encrypted_data).decode()
        
        return None

secret_manager = SecretManager()
