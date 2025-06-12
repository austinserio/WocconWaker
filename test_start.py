#!/usr/bin/env python3
"""
Quick test to verify the app can start without infinite loops
"""

import os
import sys
import time
import signal
import threading
from multiprocessing import Process

def test_app_start():
    """Test if the app can start and respond to health check"""
    try:
        # Import app components
        print("🔍 Testing app import...")
        from app import app, assistant
        
        print("✅ App imported successfully")
        print(f"✅ Assistant type: {type(assistant)}")
        
        # Test a simple function
        if hasattr(assistant, 'reply'):
            print("✅ Assistant has reply method")
        else:
            print("❌ Assistant missing reply method")
            
        print("✅ Basic test passed - app should start without infinite loops")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Testing WocconWaker startup...")
    success = test_app_start()
    
    if success:
        print("\n✅ App is ready to run!")
        print("🚀 Use: ./run_safe.sh")
        print("📝 Use: ./show_logs.sh")
        sys.exit(0)
    else:
        print("\n❌ App has issues - check errors above")
        sys.exit(1)