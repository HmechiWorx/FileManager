import hashlib

def get_machine_id():
    """
    The client will see this machine ID in the app popup and send it to the developer.
    """
    machine_id = input("Enter the machine ID shown by the client application: ").strip()
    return machine_id

def generate_license_key(machine_id, secret="MECHIWORK-2026-SECRET"):
    """
    Generates a secure license key for the given machine ID using a secret.
    """
    data = f"{machine_id}:{secret}"
    key = hashlib.sha256(data.encode()).hexdigest().upper()
    # Optionally, format the key for readability
    return "-".join([key[i:i+8] for i in range(0, 32, 8)])

def main():
    print("=== License Key Generator ===")
    machine_id = get_machine_id()
    license_key = generate_license_key(machine_id)
    print(f"\nGenerated license key for this machine:\n{license_key}\n")
    print("Give this key to the client to activate their application.")

if __name__ == "__main__":
    main()
