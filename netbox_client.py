# netbox_client.py
import requests
from typing import Any, Dict, Iterable, List, Optional

class NetBoxClient:
    def __init__(self, base_url: str, token: str, verify_ssl: bool = False):
        """
        :param base_url: e.g., 'https://netbox.lab.local/api'
        :param token: NetBox API token
        :param verify_ssl: False for self-signed (local lab). Prefer True with CA bundle in production.
        """
        self.base_url = base_url.rstrip('/') + '/'
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json'
        })
        self.verify_ssl = verify_ssl

    def _url(self, endpoint: str) -> str:
        return f'{self.base_url}{endpoint.lstrip("/")}'

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None):
        return self.session.get(self._url(endpoint), params=params, verify=self.verify_ssl)

    def post(self, endpoint: str, json: Any):
        return self.session.post(self._url(endpoint), json=json, verify=self.verify_ssl)

    def patch(self, endpoint: str, json: Any):
        return self.session.patch(self._url(endpoint), json=json, verify=self.verify_ssl)


def nb_get_all(nbc: NetBoxClient, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Paginate a NetBox list endpoint using limit/next cursor.
    """
    params = dict(params or {})
    params.setdefault('limit', 1000)  # respect server MAX_PAGE_SIZE
    results: List[Dict[str, Any]] = []

    r = nbc.get(endpoint, params=params); r.raise_for_status()
    data = r.json()
    results.extend(data.get('results', []))
    next_url = data.get('next')

    while next_url:
        r = nbc.session.get(next_url, verify=nbc.verify_ssl); r.raise_for_status()
        data = r.json()
        results.extend(data.get('results', []))
        next_url = data.get('next')

    return results


def nb_bulk_create(nbc: NetBoxClient, endpoint: str, objects: Iterable[Dict[str, Any]], batch_size: int = 400):
    """
    Bulk-create in batches to reduce API calls and payload size.
    """
    objs = list(objects)
    for i in range(0, len(objs), batch_size):
        batch = objs[i:i+batch_size]
        r = nbc.post(endpoint, json=batch)
        r.raise_for_status()
