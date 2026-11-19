import argparse
from ipaddress import IPv4Address
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Build a Wazuh CDB list of IPv4 addresses.")
    parser.add_argument("feed", nargs="?", type=Path, help="IPv4 ipset with one address per line")
    parser.add_argument("--test-ip", type=IPv4Address, help="IPv4 address of the dedicated lab client")
    args = parser.parse_args()

    addresses = set()
    if args.feed is not None:
        try:
            with args.feed.open(encoding="utf-8") as feed:
                for number, line in enumerate(feed, start=1):
                    entry = line.partition("#")[0].strip()
                    if entry:
                        try:
                            addresses.add(IPv4Address(entry))
                        except ValueError as exc:
                            parser.error(f"{args.feed}:{number}: {exc}")
        except (OSError, UnicodeError) as exc:
            parser.error(str(exc))

    if args.test_ip is not None:
        addresses.add(args.test_ip)
    if not addresses:
        parser.error("provide a feed with IPv4 addresses or --test-ip")

    for address in sorted(addresses):
        print(f"{address}:")


if __name__ == "__main__":
    main()
