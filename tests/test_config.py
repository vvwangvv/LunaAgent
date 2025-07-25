def test_load_config():
    from hyperpyyaml import load_hyperpyyaml

    with open("luna_agent/conf/default.yaml", "r") as f:
        config = load_hyperpyyaml(f)
    print("config loaded successfully")
    return config


if __name__ == "__main__":
    test_load_config()
