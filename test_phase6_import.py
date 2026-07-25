#!/usr/bin/env python
"""Test script to verify PHASE 6 changes"""
import sys
sys.path.insert(0, 'core')
sys.path.insert(0, 'providers')

print("Testing canonical provider imports...")
try:
    from windagent_providers import (
        AnthropicProviderAdapter,
        GoogleGeminiProviderAdapter,
        OllamaProviderAdapter,
        OpenAIProviderAdapter,
        MistralProviderAdapter,
        NvidiaNimAdapter,
        OpenRouterAdapter,
        LocalOllamaManager
    )
    print("[PASS] All canonical providers imported successfully")
except ImportError as e:
    print(f"[FAIL] Failed to import canonical providers: {e}")
    sys.exit(1)

print("\nTesting legacy adapter removal...")
try:
    from windagent_providers import LegacyAnthropicAdapter
    print("[FAIL] ERROR: LegacyAnthropicAdapter still exists")
    sys.exit(1)
except ImportError:
    print("[PASS] LegacyAnthropicAdapter removed")

try:
    from windagent_providers import LegacyGoogleAdapter
    print("[FAIL] ERROR: LegacyGoogleAdapter still exists")
    sys.exit(1)
except ImportError:
    print("[PASS] LegacyGoogleAdapter removed")

try:
    from windagent_providers import LegacyOllamaAdapter
    print("[FAIL] ERROR: LegacyOllamaAdapter still exists")
    sys.exit(1)
except ImportError:
    print("[PASS] LegacyOllamaAdapter removed")

print("\nTesting version metadata...")
import windagent_providers
print(f"  Version: {windagent_providers.__version__}")
print(f"  Architecture Version: {windagent_providers.__architecture_version__}")
print(f"  Protocol Version: {windagent_providers.__provider_protocol_version__}")

if windagent_providers.__version__ == "2.0.0":
    print("[PASS] Version metadata correct")
else:
    print(f"[FAIL] Version should be 2.0.0, got {windagent_providers.__version__}")
    sys.exit(1)

if windagent_providers.__architecture_version__ == "v2":
    print("[PASS] Architecture version correct")
else:
    print(f"[FAIL] Architecture version should be v2, got {windagent_providers.__architecture_version__}")
    sys.exit(1)

print("\n[PASS] All PHASE 6 checks passed!")
