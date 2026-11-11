#!/usr/bin/env python3
"""
Append runs from Garmin Connect to data/activities.json (Strava fallback).

Usage:
    python garmin_fetch.py                    # since latest cached activity
    python garmin_fetch.py --since 2026-09-01

First run prompts for Garmin email/password (+ MFA); tokens are saved to
~/.garminconnect. GARMIN_EMAIL / GARMIN_PASSWORD (env or .env) skip the prompt. Without a
TTY, MFA is two-step: run once, then rerun with --mfa <code>.
"""
import argparse

from dotenv import load_dotenv

from src.garmin import fetch_garmin_activities, login

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=None, help="YYYY-MM-DD")
    parser.add_argument("--mfa", default=None, help="MFA code to finish a pending login")
    args = parser.parse_args()
    load_dotenv(".env")
    fetch_garmin_activities(login(args.mfa), start_date=args.since)
