import requests
import time
import json

BASE_URL = "http://localhost:2357/api/v1"

def test_msaf_health():
    print("\n--- Testing Standalone MSAF Health Check ---")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["service"] == "msaf-standalone"

def test_msaf_process_retry_false():
    print("\n--- Testing Direct MSAF Process with retry_flag=False ---")
    payload = {
        "jobID": f"test-job-direct-false-{int(time.time())}",
        "tco_file_url": "file://c:/AI-projects/afg_agno/AFGEstimateAnalyser/data/uploads/sample.xlsx",
        "retry_flag": False
    }
    response = requests.post(f"{BASE_URL}/msaf_process", json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["jobID"] == payload["jobID"]
    assert "Hi there" in response.json()["response"]

def test_msaf_process_retry_true():
    print("\n--- Testing Direct MSAF Process with retry_flag=True ---")
    payload = {
        "jobID": f"test-job-direct-true-{int(time.time())}",
        "retry_flag": True
    }
    response = requests.post(f"{BASE_URL}/msaf_process", json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["jobID"] == payload["jobID"]
    assert "Hi there" in response.json()["response"]

if __name__ == "__main__":
    try:
        test_msaf_health()
        test_msaf_process_retry_false()
        test_msaf_process_retry_true()
        print("\nAll Standalone MSAF API tests passed!")
    except Exception as e:
        print(f"\nTests failed: {e}")
