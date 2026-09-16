from .store import Store


def main():
    store = Store()
    if not store.ai_due():
        return
    store.reserve_ai_attempt()


if __name__ == "__main__":
    main()
