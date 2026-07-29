from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_health_does_not_expose_key():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()


def test_demo_and_create_analysis():
    assert client.get("/api/demo").status_code == 200
    response = client.post("/api/analyses?demo_mode=true")
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"]
    result = client.get(f"/api/analyses/{body['analysis_id']}")
    assert result.status_code == 200


def test_template_download():
    response = client.get("/api/template.csv")
    assert response.status_code == 200
    assert "prepared_qty" in response.text
