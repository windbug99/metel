from agent.pipeline_links import extract_pipeline_links, persist_pipeline_failure_link


def test_extract_pipeline_links_from_for_each_artifacts():
    artifacts = {
        "n2": {
            "item_count": 2,
            "item_results": [
                {
                    "n2_1": {"event_id": "evt-1"},
                    "n2_2": {"id": "page-1"},
                    "n2_3": {"issueCreate": {"issue": {"id": "issue-1"}}},
                },
                {
                    "n2_1": {"event_id": "evt-2"},
                    "n2_2": {"page_id": "page-2"},
                    "n2_3": {"id": "issue-2"},
                },
            ],
        }
    }
    rows = extract_pipeline_links(user_id="user-1", pipeline_run_id="prun_1", artifacts=artifacts)
    assert len(rows) == 2
    assert rows[0]["event_id"] == "evt-1"
    assert rows[0]["notion_page_id"] == "page-1"
    assert rows[0]["linear_issue_id"] == "issue-1"
    assert rows[0]["error_code"] is None
    assert rows[0]["compensation_status"] == "not_required"
    assert rows[1]["event_id"] == "evt-2"
    assert rows[1]["notion_page_id"] == "page-2"
    assert rows[1]["linear_issue_id"] == "issue-2"


def test_persist_pipeline_failure_link_returns_true_on_empty_event():
    assert persist_pipeline_failure_link(user_id="u1", event_id="", run_id="prun", status="failed") is True


def test_extract_pipeline_links_from_nested_data_payloads():
    artifacts = {
        "n2": {
            "item_count": 1,
            "item_results": [
                {
                    "n2_1": {"event_id": "evt-3"},
                    "n2_2": {"ok": True, "data": {"id": "page-3", "url": "https://notion.so/page-3"}},
                    "n2_3": {
                        "ok": True,
                        "data": {"issueCreate": {"issue": {"id": "issue-3", "url": "https://linear.app/issue-3"}}},
                    },
                }
            ],
        }
    }
    rows = extract_pipeline_links(user_id="user-1", pipeline_run_id="prun_2", artifacts=artifacts)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "evt-3"
    assert rows[0]["notion_page_id"] == "page-3"
    assert rows[0]["linear_issue_id"] == "issue-3"
