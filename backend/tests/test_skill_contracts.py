from agent.skill_contracts import (
    infer_skill_name_from_runtime_tools,
    list_contract_files,
    load_contract,
    runtime_tools_for_services,
    service_for_skill,
    validate_all_contracts,
    validate_contract,
)


def test_contract_files_exist_for_core_skills():
    files = list_contract_files()
    names = {file.name for file in files}
    assert "notion_page_create.json" in names
    assert "notion_page_search.json" in names
    assert "notion_page_update.json" in names
    assert "notion_page_delete.json" in names
    assert "linear_issue_create.json" in names
    assert "linear_issue_search.json" in names
    assert "linear_issue_update.json" in names
    assert "linear_issue_delete.json" in names
    assert "web_url_fetch_text.json" in names


def test_all_skill_contracts_validate():
    total, failures = validate_all_contracts()
    assert total >= 8
    assert failures == {}


def test_validate_contract_requires_examples():
    contract = {
        "name": "notion.page_create",
        "version": "1.0.0",
        "summary": "x",
        "provider": {"service": "notion"},
        "autofill": {},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "examples": [],
    }
    errors = validate_contract(contract)
    assert any("examples" in error for error in errors)


def test_load_contract_returns_dict_for_valid_file():
    files = list_contract_files()
    assert files
    payload = load_contract(files[0])
    assert isinstance(payload, dict)


def test_runtime_tools_for_services_uses_contracts():
    notion_tools = set(runtime_tools_for_services(["notion"]))
    linear_tools = set(runtime_tools_for_services(["linear"]))
    assert "notion_create_page" in notion_tools
    assert "notion_search" in notion_tools
    assert "linear_create_issue" in linear_tools
    assert "linear_search_issues" in linear_tools


def test_service_for_skill_reads_contract_provider():
    assert service_for_skill("notion.page_create") == "notion"
    assert service_for_skill("linear.issue_search") == "linear"
    assert service_for_skill("unknown.skill") is None


def test_infer_skill_name_from_runtime_tools_prefers_exact_unique_match():
    assert infer_skill_name_from_runtime_tools(["notion_create_page"]) == "notion.page_create"
    assert infer_skill_name_from_runtime_tools(["notion_search"]) == "notion.page_search"


def test_infer_skill_name_from_runtime_tools_returns_none_for_ambiguous_match():
    # linear.issue_update / linear.issue_delete share the same tool set.
    inferred = infer_skill_name_from_runtime_tools(["linear_search_issues", "linear_update_issue"])
    assert inferred is None
