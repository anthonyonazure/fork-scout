# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub: open the **Security** tab of this repository and choose **Report a vulnerability**. Do not open a public issue for something that could be exploited. I will acknowledge a report within a few days.

## What counts

fork-scout reads code written by strangers, so the interesting bugs are the ones where reading it goes wrong:

- A way for a fork's content to make fork-scout run code, write outside its own folders, or leak your credentials.
- A way to get past the gate, so that `snapshot.py`, `fork.py` or `build.py` act on a fork that was not scanned and reviewed at its current commit.
- A scan rule that a malicious fork can trivially slip past (reports of this kind are welcome, but note that pattern matching can never be complete).

## Design limits

fork-scout does not prove code is safe. "No red flags found" means the pattern checks and one reviewer found nothing, no more. See the "How the safety works" section of the README.
