from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_create_knowledge_base_rejects_empty_name() -> None:
    response = client.post(
        "/knowledge-bases",
        json={
            "name": "",
            "description": "无效知识库",
        },
    )

    assert response.status_code == 422