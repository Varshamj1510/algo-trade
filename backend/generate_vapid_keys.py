import base64
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / '.env'


def _encode_urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _read_environment() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding='utf-8').splitlines()


def generate_vapid_keys() -> bool:
    lines = _read_environment()
    values: dict[str, str] = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        values[name.strip()] = value.strip()

    has_public = bool(values.get('VAPID_PUBLIC_KEY'))
    has_private = bool(values.get('VAPID_PRIVATE_KEY'))
    if has_public != has_private:
        raise ValueError('Both VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY must be configured together.')
    if has_public:
        return False

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_numbers = private_key.private_numbers()
    public_numbers = private_numbers.public_numbers
    private_raw = private_numbers.private_value.to_bytes(32, 'big')
    public_raw = (
        b'\x04'
        + public_numbers.x.to_bytes(32, 'big')
        + public_numbers.y.to_bytes(32, 'big')
    )
    additions = [
        f'VAPID_PUBLIC_KEY={_encode_urlsafe(public_raw)}',
        f'VAPID_PRIVATE_KEY={_encode_urlsafe(private_raw)}',
        'VAPID_SUBJECT=mailto:admin@alphamind.local',
    ]
    if values.get('VAPID_SUBJECT'):
        additions[2] = f"VAPID_SUBJECT={values['VAPID_SUBJECT']}"
    lines.extend(additions)

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=ENV_PATH.parent,
            prefix='.vapid-',
            suffix='.tmp',
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write('\n'.join(lines) + '\n')
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, ENV_PATH)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return True


if __name__ == '__main__':
    created = generate_vapid_keys()
    print('Generated VAPID keys in the local .env file.' if created else 'VAPID keys are already configured.')
