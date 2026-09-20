import config_manager

if __name__ == '__main__':
    cfg = config_manager.ConfigManager()
    print("Rules loaded:", len(cfg.get_rules()))
    for r in cfg.get_rules():
        print(f" - [{r.id}] {r.name}: {r.process_names}, action={r.action}")