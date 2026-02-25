from scripts.check_supabase_connectivity import _extract_host, _is_reachable_status, _rest_url


def test_extract_host():
    assert _extract_host("https://abc.supabase.co") == "abc.supabase.co"
    assert _extract_host("http://localhost:54321/") == "localhost"
    assert _extract_host("") == ""


def test_rest_url():
    assert _rest_url("https://abc.supabase.co") == "https://abc.supabase.co/rest/v1/"
    assert _rest_url("https://abc.supabase.co/") == "https://abc.supabase.co/rest/v1/"


def test_is_reachable_status():
    assert _is_reachable_status(200) is True
    assert _is_reachable_status(401) is True
    assert _is_reachable_status(404) is True
    assert _is_reachable_status(503) is False
