#!/usr/bin/env python3
"""
Test script for improved payload injection system
"""

import os
import sys
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from payload_injection_system import MultiVectorInjector, InjectionPoint, PayloadComponent, InjectionStrategy
from environment_manager import EnvironmentManager
from error_handler import ErrorHandler, ValidationError, FileOperationError
from file_manager import FileManager

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('test_payload_injection.log')
        ]
    )

def test_environment_manager():
    """Test EnvironmentManager functionality"""
    print("Testing EnvironmentManager...")
    
    env_manager = EnvironmentManager()
    
    # Test environment variables
    lhost = env_manager.get_lhost()
    lport = env_manager.get_lport()
    print(f"LHOST: {lhost}")
    print(f"LPORT: {lport}")
    
    # Test environment validation
    validation_results = env_manager.validate_environment()
    print(f"Environment validation: {validation_results}")
    
    # Test tool paths
    tool_paths = env_manager.get_tool_paths()
    print(f"Tool paths: {tool_paths}")
    
    # Test environment info
    env_info = env_manager.get_environment_info()
    print(f"Environment info: {env_info}")
    
    print("EnvironmentManager tests completed\n")

def test_error_handler():
    """Test ErrorHandler functionality"""
    print("Testing ErrorHandler...")
    
    error_handler = ErrorHandler()
    
    # Test command execution
    ok, output = error_handler.run_command(['echo', 'test'], timeout=10)
    print(f"Command test result: {ok}, output: {output}")
    
    # Test file validation
    with tempfile.NamedTemporaryFile() as tmp_file:
        tmp_path = Path(tmp_file.name)
        result = error_handler.validate_file_path(tmp_path, must_exist=True)
        print(f"File validation result: {result}")
    
    # Test directory validation
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = error_handler.validate_directory_path(tmp_path, must_exist=True, must_be_writable=True)
        print(f"Directory validation result: {result}")
    
    print("ErrorHandler tests completed\n")

def test_file_manager():
    """Test FileManager functionality"""
    print("Testing FileManager...")
    
    file_manager = FileManager()
    
    # Test safe text operations
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
        test_content = "Test content with unicode: éñç"
        tmp_file.write(test_content)
    
    try:
        # Test safe read
        content = file_manager.safe_read_text(tmp_path)
        print(f"Safe read result: {content == test_content}")
        
        # Test safe write
        new_content = "New test content"
        file_manager.safe_write_text(tmp_path, new_content)
        read_back = file_manager.safe_read_text(tmp_path)
        print(f"Safe write result: {read_back == new_content}")
        
        # Test file size
        size_mb = file_manager.get_file_size_mb(tmp_path)
        print(f"File size: {size_mb:.6f} MB")
        
    finally:
        # Cleanup
        if tmp_path.exists():
            tmp_path.unlink()
    
    # Test temporary workspace
    with file_manager.temporary_workspace() as temp_dir:
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")
        print(f"Temporary workspace test: {test_file.exists()}")
    
    print("FileManager tests completed\n")

def test_multi_vector_injector():
    """Test MultiVectorInjector functionality"""
    print("Testing MultiVectorInjector...")
    
    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir)
        
        # Initialize injector
        injector = MultiVectorInjector(workspace)
        
        # Test environment info
        env_info = injector.get_environment_info()
        print(f"Injector environment info: {env_info}")
        
        # Test target config validation
        valid_config = {
            'lhost': '127.0.0.1',
            'lport': '4444'
        }
        
        invalid_config = {
            'lhost': 'invalid.ip',
            'lport': '99999'
        }
        
        print(f"Valid config validation: {injector.validate_target_config(valid_config)}")
        print(f"Invalid config validation: {injector.validate_target_config(invalid_config)}")
        
        # Test IP validation
        print(f"Valid IP test: {injector._is_valid_ip('192.168.1.1')}")
        print(f"Invalid IP test: {injector._is_valid_ip('invalid')}")
        
        # Test injection strategy creation
        injection_points = [
            InjectionPoint(
                location_type="activity",
                target_name="com.example.MainActivity",
                method_name="onCreate",
                priority=10,
                stealth_level="high",
                modification_type="smali_injection"
            )
        ]
        
        try:
            strategy = injector.create_injection_strategy(injection_points, valid_config)
            print(f"Strategy created: {strategy.strategy_name}")
            print(f"Strategy success probability: {strategy.success_probability}")
        except Exception as e:
            print(f"Strategy creation failed: {e}")
    
    print("MultiVectorInjector tests completed\n")

def test_integration():
    """Test integration between components"""
    print("Testing integration...")
    
    # Test that all components work together
    env_manager = EnvironmentManager()
    error_handler = ErrorHandler()
    file_manager = FileManager()
    
    # Test environment validation
    validation_results = env_manager.validate_environment()
    print(f"Integration environment validation: {validation_results}")
    
    # Test error handling with environment
    lhost = env_manager.get_lhost()
    lport = env_manager.get_lport()
    print(f"Integration LHOST/LPORT: {lhost}:{lport}")
    
    # Test file operations with error handling
    with file_manager.temporary_workspace() as temp_dir:
        test_file = temp_dir / "integration_test.txt"
        try:
            file_manager.safe_write_text(test_file, "Integration test content")
            content = file_manager.safe_read_text(test_file)
            print(f"Integration file test: {content == 'Integration test content'}")
        except Exception as e:
            print(f"Integration file test failed: {e}")
    
    print("Integration tests completed\n")

def main():
    """Main test function"""
    print("Starting payload injection system tests...\n")
    
    setup_logging()
    
    try:
        test_environment_manager()
        test_error_handler()
        test_file_manager()
        test_multi_vector_injector()
        test_integration()
        
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())