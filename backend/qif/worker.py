"""Retired QIF worker entry point. Recovery belongs to the schema-set service."""
RETIRED_MESSAGE = (
    'The separate QIF worker is retired. Start backend.qif.app through the '
    'deployment service manifest or start-depo-services.ps1; the schema-set '
    'service owns recovery and execution. See INSTALLATION.md.'
)


def run():
    raise RuntimeError(RETIRED_MESSAGE)


if __name__ == '__main__':
    raise SystemExit(RETIRED_MESSAGE)
