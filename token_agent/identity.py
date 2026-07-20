import os
import urllib.request
import urllib.parse
from typing import Optional
from cryptography import x509
from cryptography.hazmat.primitives import serialization
import hashlib
import base64
import logging

logger = logging.getLogger(__name__)

# Constants
CERT_FILE = os.environ.get("WORKLOAD_CERTIFICATE_FILE", "/var/run/secrets/workload-spiffe-credentials/certificates.pem")
METADATA_IDENTITY_URL = os.environ.get("METADATA_IDENTITY_URL", "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity")
DEFAULT_AUDIENCE = os.environ.get("AUDIENCE", "https://example.com")

def get_certificate_fingerprint(cert_path: str = CERT_FILE) -> Optional[str]:
    """Reads a PEM certificate and returns its SHA256 fingerprint."""
    if not cert_path or not os.path.exists(cert_path):
        logger.warning(f"Certificate file not found at {cert_path}. Will attempt to get unbound token.")
        return None
    try:
        logger.info(f"Certificate file found at: {cert_path}")
        with open(cert_path, "rb") as f:
            pem_data = f.read()
        cert = x509.load_pem_x509_certificate(pem_data)
        der_data = cert.public_bytes(serialization.Encoding.DER)
        sha256_hash = hashlib.sha256(der_data).digest()
        b64_encoded = base64.b64encode(sha256_hash).decode('utf-8')
        unpadded = b64_encoded.rstrip('=')
        return unpadded
    except Exception as e:
        logger.error(f"Failed to compute fingerprint from {cert_path}: {e}")
        return None

def get_identity_token(audience: str, fingerprint: Optional[str] = None) -> str:
    """Calls the Google Metadata Server to retrieve the identity token."""
    params = {
        "audience": audience,
        "format": "full"
    }
    if fingerprint:
        params["bindCertificateFingerprint"] = fingerprint
        
    url = METADATA_IDENTITY_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Metadata-Flavor", "Google")
    try:
        with urllib.request.urlopen(req) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to get identity token from metadata server: {e}")
        raise

def fetch_gcp_identity_token(audience: Optional[str] = None) -> str:
    """Helper function to fetch the GCP identity token with target audience."""
    target_audience = audience or os.environ.get("AUDIENCE", DEFAULT_AUDIENCE)
    logger.info(f"Retrieving GCP agent identity token for audience: {target_audience}")
    
    fingerprint = get_certificate_fingerprint(CERT_FILE)
    if fingerprint:
        logger.info(f"Using bound token with fingerprint: {fingerprint}")
    else:
        logger.info("Using unbound token")
        
    return get_identity_token(target_audience, fingerprint)
