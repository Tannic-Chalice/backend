#!/usr/bin/env python3
"""
Twilio Messaging API Test Suite
Test all messaging endpoints to verify integration
"""

import requests
import json
from typing import Dict, Any
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
MESSAGING_BASE = f"{BASE_URL}/messaging"

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
END = "\033[0m"


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{BLUE}{'='*60}")
    print(f"{title}")
    print(f"{'='*60}{END}\n")


def print_success(msg: str):
    """Print success message"""
    print(f"{GREEN}✓ {msg}{END}")


def print_error(msg: str):
    """Print error message"""
    print(f"{RED}✗ {msg}{END}")


def print_info(msg: str):
    """Print info message"""
    print(f"{YELLOW}ℹ {msg}{END}")


def print_json(data: Dict[Any, Any]):
    """Print formatted JSON"""
    print(json.dumps(data, indent=2))


def test_health_check():
    """Test health check endpoint"""
    print_section("TEST 1: Health Check")
    
    try:
        response = requests.get(f"{MESSAGING_BASE}/health")
        
        if response.status_code == 200:
            print_success("Health check passed")
            data = response.json()
            print_json(data)
            return True
        else:
            print_error(f"Health check failed with status {response.status_code}")
            print_json(response.json())
            return False
            
    except Exception as e:
        print_error(f"Health check error: {str(e)}")
        return False


def test_send_single_sms(phone: str, message: str = "Test SMS from MSGP System"):
    """Test sending single SMS"""
    print_section("TEST 2: Send Single SMS")
    
    payload = {
        "to_phone": phone,
        "message": message,
        "message_type": "general"
    }
    
    print_info(f"Sending SMS to: {phone}")
    print_info(f"Message: {message}")
    
    try:
        response = requests.post(
            f"{MESSAGING_BASE}/send-sms",
            json=payload
        )
        
        if response.status_code == 200:
            print_success("SMS sent successfully")
            data = response.json()
            print_json(data)
            return data.get("message_sid") if data.get("success") else None
        else:
            print_error(f"Failed to send SMS: {response.status_code}")
            print_json(response.json())
            return None
            
    except Exception as e:
        print_error(f"SMS send error: {str(e)}")
        return None


def test_send_bulk_sms(phones: list):
    """Test sending bulk SMS"""
    print_section("TEST 3: Send Bulk SMS")
    
    payload = {
        "phone_numbers": phones,
        "message": "Bulk message test from MSGP System",
        "message_type": "notification"
    }
    
    print_info(f"Sending SMS to {len(phones)} recipients")
    
    try:
        response = requests.post(
            f"{MESSAGING_BASE}/send-bulk-sms",
            json=payload
        )
        
        if response.status_code == 200:
            print_success("Bulk SMS sent")
            data = response.json()
            print_json(data)
            return True
        else:
            print_error(f"Failed to send bulk SMS: {response.status_code}")
            print_json(response.json())
            return False
            
    except Exception as e:
        print_error(f"Bulk SMS error: {str(e)}")
        return False


def test_send_alert(phone: str):
    """Test sending alert SMS"""
    print_section("TEST 4: Send Alert SMS")
    
    payload = {
        "to_phone": phone,
        "message": "System maintenance scheduled for tonight"
    }
    
    print_info(f"Sending alert to: {phone}")
    
    try:
        response = requests.post(
            f"{MESSAGING_BASE}/send-alert",
            json=payload
        )
        
        if response.status_code == 200:
            print_success("Alert SMS sent successfully")
            data = response.json()
            print_json(data)
            return data.get("message_sid") if data.get("success") else None
        else:
            print_error(f"Failed to send alert: {response.status_code}")
            print_json(response.json())
            return None
            
    except Exception as e:
        print_error(f"Alert send error: {str(e)}")
        return None


def test_sms_status(message_sid: str):
    """Test checking SMS status"""
    print_section("TEST 5: Check SMS Status")
    
    if not message_sid:
        print_error("No message SID provided, skipping status check")
        return False
    
    print_info(f"Checking status for message: {message_sid}")
    
    try:
        response = requests.get(
            f"{MESSAGING_BASE}/sms-status/{message_sid}"
        )
        
        if response.status_code == 200:
            print_success("Status retrieved successfully")
            data = response.json()
            print_json(data)
            return True
        else:
            print_error(f"Failed to get status: {response.status_code}")
            print_json(response.json())
            return False
            
    except Exception as e:
        print_error(f"Status check error: {str(e)}")
        return False


def test_invalid_phone():
    """Test error handling with invalid phone"""
    print_section("TEST 6: Error Handling (Invalid Phone)")
    
    payload = {
        "to_phone": "invalid",
        "message": "This should fail"
    }
    
    print_info("Sending SMS with invalid phone number")
    
    try:
        response = requests.post(
            f"{MESSAGING_BASE}/send-sms",
            json=payload
        )
        
        if response.status_code != 200:
            print_success("Error handling working correctly")
            print_json(response.json())
            return True
        else:
            print_error("Should have returned error for invalid phone")
            return False
            
    except Exception as e:
        print_error(f"Error test error: {str(e)}")
        return False


def main():
    """Run all tests"""
    print(f"\n{BLUE}")
    print("╔" + "═"*58 + "╗")
    print("║" + " "*15 + "TWILIO MESSAGING API TEST SUITE" + " "*13 + "║")
    print("║" + " "*17 + f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" + " "*20 + "║")
    print("╚" + "═"*58 + "╝")
    print(f"{END}")
    
    # Test 1: Health Check
    health_ok = test_health_check()
    
    if not health_ok:
        print_error("Cannot proceed: Twilio not accessible")
        return
    
    # Get test phone number
    test_phone = input(f"\n{YELLOW}Enter phone number for testing (e.g., 9876543210): {END}").strip()
    if not test_phone:
        print_error("No phone number provided, using default test")
        test_phone = "9876543210"
    
    # Test 2: Single SMS
    message_sid = test_send_single_sms(test_phone)
    
    # Test 3: Bulk SMS
    test_send_bulk_sms([test_phone, test_phone])
    
    # Test 4: Alert SMS
    alert_sid = test_send_alert(test_phone)
    
    # Test 5: Status Check
    if message_sid:
        test_sms_status(message_sid)
    
    # Test 6: Error Handling
    test_invalid_phone()
    
    # Summary
    print_section("TEST SUMMARY")
    print_success("All messaging endpoints tested")
    print_info("Check results above for any failures")
    print_info(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n{BLUE}{'='*60}")
    print("✓ Testing Complete")
    print(f"{'='*60}{END}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Tests interrupted by user{END}\n")
    except Exception as e:
        print(f"\n{RED}Test suite error: {str(e)}{END}\n")
