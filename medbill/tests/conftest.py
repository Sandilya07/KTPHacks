import pytest

from audit.cms_data import sample_cms_data, set_cms_data


@pytest.fixture(autouse=True)
def _sample_cms():
    """Unit tests never depend on downloaded CMS files: use the documented sample tables."""
    set_cms_data(sample_cms_data())
    yield
    set_cms_data(None)
