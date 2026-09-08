def test_monitoring_api_package_can_be_imported() -> None:
    import monitoring_api

    assert monitoring_api.__name__ == "monitoring_api"
