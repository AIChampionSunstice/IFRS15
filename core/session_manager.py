import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional
import json
from datetime import datetime
import re
from difflib import SequenceMatcher

class SessionManager:
    DATA_DIR = Path("data/contracts")
    
    @staticmethod
    def _ensure_data_dir():
        SessionManager.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def _get_contracts_file() -> Path:
        return SessionManager.DATA_DIR / "contracts.json"
    
    @staticmethod
    def _normalize_company_name(name: str) -> str:
        if not name:
            return ""

        normalized = name.lower().strip()
        normalized = re.sub(r'\([^)]*\)', '', normalized)
        legal_suffixes = [
            'limited', 'ltd', 'llc', 'inc', 'incorporated', 'corp', 'corporation',
            's.a.s', 'sas', 's.a', 'sa', 'sarl', 'gmbh', 'plc', 'private limited',
            'pte ltd', 'pte', 'pvt', 'berhad', 'bhd', 'co', 'company',
            'associates', 'associes', 'holdings', 'group', 'international'
        ]
        
        for suffix in legal_suffixes:
            pattern = r'\b' + re.escape(suffix) + r'\b\.?$'
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        normalized = re.sub(r'[^\w\s-]', ' ', normalized)

        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    @staticmethod
    def _calculate_similarity(name1: str, name2: str) -> float:
        norm1 = SessionManager._normalize_company_name(name1)
        norm2 = SessionManager._normalize_company_name(name2)
        
        if not norm1 or not norm2:
            return 0.0

        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        return similarity
    
    @staticmethod
    def _find_similar_contract(client_name: str, similarity_threshold: float = 0.85) -> Optional[int]:
        contracts = st.session_state.contracts
        
        for idx, existing_contract in enumerate(contracts):
            existing_name = existing_contract.get('Client Name', '')

            if client_name.strip().lower() == existing_name.strip().lower():
                return idx

            similarity = SessionManager._calculate_similarity(client_name, existing_name)
            
            if similarity >= similarity_threshold:
                print(f"Similarité détectée ({similarity*100:.1f}%) : '{client_name}' ≈ '{existing_name}'")
                return idx
        
        return None
    
    @staticmethod
    def _load_contracts_from_disk() -> List[Dict]:
        SessionManager._ensure_data_dir()
        contracts_file = SessionManager._get_contracts_file()
        
        if contracts_file.exists():
            try:
                with open(contracts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('contracts', [])
            except Exception as e:
                print(f"Erreur chargement contracts: {e}")
                return []
        return []
    
    @staticmethod
    def _save_contracts_to_disk(contracts: List[Dict]):
        SessionManager._ensure_data_dir()
        contracts_file = SessionManager._get_contracts_file()
        
        try:
            data = {
                'contracts': contracts,
                'last_updated': datetime.now().isoformat(),
                'count': len(contracts)
            }
            with open(contracts_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erreur sauvegarde contracts: {e}")
    
    @staticmethod
    def init_session():
        if 'contracts' not in st.session_state:
            st.session_state.contracts = SessionManager._load_contracts_from_disk()
        
        if 'current_contract' not in st.session_state:
            st.session_state.current_contract = None
            
        if 'analysis_results' not in st.session_state:
            st.session_state.analysis_results = {}
            
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = []
            
        if 'workspace_path' not in st.session_state:
            st.session_state.workspace_path = None
            
        if 'config' not in st.session_state:
            st.session_state.config = {
                'agi_threshold': 10.0,
                'auto_classify': True,
                'show_evidence': True,
                'export_format': 'excel',
                'similarity_threshold': 0.85
            }
    
    @staticmethod
    def add_contract(contract_data: Dict):
        client_name = contract_data.get('Client Name', 'Unknown')
        similarity_threshold = SessionManager.get_config('similarity_threshold')
        existing_index = SessionManager._find_similar_contract(client_name, similarity_threshold)
        
        contract_data['timestamp'] = datetime.now().isoformat()
        
        if existing_index is not None:
            existing_name = st.session_state.contracts[existing_index].get('Client Name')
            contract_data['id'] = st.session_state.contracts[existing_index]['id']
            st.session_state.contracts[existing_index] = contract_data

            if client_name.lower() != existing_name.lower():
                st.warning(f" Contrat **{client_name}** fusionné avec **{existing_name}** (contrat similaire détecté)")
            else:
                st.info(f" Contrat **{client_name}** mis à jour (existait déjà)")
        else:
            contract_data['id'] = len(st.session_state.contracts)
            st.session_state.contracts.append(contract_data)
            st.success(f" Nouveau contrat ajouté : **{client_name}**")
        
        st.session_state.current_contract = contract_data
        SessionManager._save_contracts_to_disk(st.session_state.contracts)
    
    @staticmethod
    def get_contracts() -> List[Dict]:
        return st.session_state.contracts
    
    @staticmethod
    def get_current_contract() -> Optional[Dict]:
        return st.session_state.current_contract
    
    @staticmethod
    def clear_session():
        st.session_state.contracts = []
        st.session_state.current_contract = None
        st.session_state.analysis_results = {}
        st.session_state.uploaded_files = []

        contracts_file = SessionManager._get_contracts_file()
        if contracts_file.exists():
            contracts_file.unlink()
    
    @staticmethod
    def update_config(key: str, value):
        st.session_state.config[key] = value
    
    @staticmethod
    def get_config(key: str):
        return st.session_state.config.get(key)
    
    @staticmethod
    def set_config(key: str, value):
        SessionManager.update_config(key, value)
    
    @staticmethod
    def export_session_data() -> str:
        export_data = {
            'contracts': st.session_state.contracts,
            'config': st.session_state.config,
            'export_date': datetime.now().isoformat()
        }
        return json.dumps(export_data, indent=2, ensure_ascii=False)