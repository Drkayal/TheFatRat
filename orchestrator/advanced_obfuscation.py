import os
import re
import random
import string
import hashlib
import struct
import base64
import binascii
import secrets
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import zipfile
import tempfile
import subprocess
import json
import math

@dataclass
class ObfuscationConfig:
    string_encryption_level: int  # 1-5
    control_flow_complexity: int  # 1-10
    dead_code_ratio: float  # 0.0-1.0
    api_redirection_level: int  # 1-3
    dynamic_key_rotation: bool
    anti_analysis_hooks: bool

@dataclass
class EncryptionKeyPair:
    primary_key: bytes
    secondary_key: bytes
    rotation_seed: int
    algorithm: str

class DynamicStringEncryption:
    """Advanced string encryption with dynamic key generation"""
    
    def __init__(self, complexity_level: int = 3):
        self.complexity_level = complexity_level
        self.key_cache = {}
        self.encryption_methods = [
            self._xor_encrypt,
            self._aes_like_encrypt,
            self._polyalphabetic_encrypt,
            self._rc4_like_encrypt,
            self._custom_matrix_encrypt
        ]
    
    def generate_dynamic_keys(self, seed: str = None) -> EncryptionKeyPair:
        """Generate dynamic encryption keys based on app context"""
        if not seed:
            seed = secrets.token_hex(16)
        
        # Generate primary key using multiple sources
        primary_entropy = (
            hashlib.sha256(seed.encode()).digest() +
            hashlib.md5(str(datetime.now().timestamp()).encode()).digest() +
            secrets.token_bytes(16)
        )
        
        primary_key = hashlib.sha512(primary_entropy).digest()[:32]
        
        # Generate secondary key with different algorithm
        secondary_entropy = (
            hashlib.blake2b(primary_key).digest() +
            hashlib.sha3_256(seed.encode()).digest()
        )
        
        secondary_key = hashlib.pbkdf2_hmac('sha256', secondary_entropy, 
                                           b'dynamic_salt', 100000)[:32]
        
        rotation_seed = struct.unpack('<I', hashlib.md5(primary_key).digest()[:4])[0]
        
        return EncryptionKeyPair(
            primary_key=primary_key,
            secondary_key=secondary_key,
            rotation_seed=rotation_seed,
            algorithm=f"DYNAMIC_V{self.complexity_level}"
        )
    
    def encrypt_string(self, plaintext: str, keys: EncryptionKeyPair) -> Dict[str, Any]:
        """Encrypt string using dynamic multi-layer encryption"""
        
        # Select encryption method based on string length and content
        method_index = (len(plaintext) + sum(ord(c) for c in plaintext)) % len(self.encryption_methods)
        encrypt_func = self.encryption_methods[method_index]
        
        # Apply multiple encryption layers
        encrypted_layers = []
        current_data = plaintext.encode('utf-8')
        
        for layer in range(self.complexity_level):
            key = self._derive_layer_key(keys, layer)
            current_data = encrypt_func(current_data, key)
            encrypted_layers.append({
                "layer": layer,
                "method": encrypt_func.__name__,
                "size": len(current_data)
            })
        
        final_encrypted = base64.b64encode(current_data).decode('ascii')
        
        return {
            "encrypted": final_encrypted,
            "layers": encrypted_layers,
            "method_index": method_index,
            "key_rotation": keys.rotation_seed % 256,
            "checksum": hashlib.md5(plaintext.encode()).hexdigest()[:8]
        }
    
    def generate_decryption_smali(self, encrypted_data: Dict[str, Any], 
                                 keys: EncryptionKeyPair) -> str:
        """Generate Smali code for runtime decryption"""
        
        class_name = f"StringDecryptor{random.randint(1000, 9999)}"
        
        # Generate key derivation code
        key_derivation_code = self._generate_key_derivation_smali(keys)
        
        # Generate decryption algorithm code
        decryption_code = self._generate_decryption_algorithm_smali(encrypted_data, keys)
        
        smali_code = f"""
.class public Lcom/android/internal/{class_name};
.super Ljava/lang/Object;

# Dynamic string decryption with key rotation
.field private static final ROTATION_SEED:I = {keys.rotation_seed}
.field private static keyCache:Ljava/util/Map;

.method static constructor <clinit>()V
    .locals 1
    new-instance v0, Ljava/util/HashMap;
    invoke-direct {{v0}}, Ljava/util/HashMap;-><init>()V
    sput-object v0, Lcom/android/internal/{class_name};->keyCache:Ljava/util/Map;
    return-void
.end method

# Main decryption method
.method public static decrypt(Ljava/lang/String;I)Ljava/lang/String;
    .locals 8
    .param p0, "encryptedData"    # Ljava/lang/String;
    .param p1, "keyRotation"    # I
    
    # Anti-debug check
    invoke-static {{}}, Lcom/android/internal/{class_name};->checkEnvironment()Z
    move-result v0
    if-nez v0, :proceed_decrypt
    const-string v0, ""
    return-object v0
    
    :proceed_decrypt
    # Generate runtime key
    invoke-static {{p1}}, Lcom/android/internal/{class_name};->deriveKey(I)[B
    move-result-object v1
    
    # Decode base64
    :try_start_decode
    invoke-static {{p0}}, Landroid/util/Base64;->decode(Ljava/lang/String;I)[B
    move-result-object v2
    :try_end_decode
    .catch Ljava/lang/Exception; {{:decode_error}}
    
    # Apply decryption layers
    invoke-static {{v2, v1}}, Lcom/android/internal/{class_name};->applyDecryptionLayers([B[B)[B
    move-result-object v3
    
    # Convert to string
    :try_start_convert
    new-instance v4, Ljava/lang/String;
    const-string v5, "UTF-8"
    invoke-direct {{v4, v3, v5}}, Ljava/lang/String;-><init>([BLjava/lang/String;)V
    return-object v4
    :try_end_convert
    .catch Ljava/lang/Exception; {{:convert_error}}
    
    :decode_error
    :convert_error
    move-exception v0
    const-string v0, ""
    return-object v0
.end method

{key_derivation_code}

{decryption_code}

# Environment check for anti-analysis
.method private static checkEnvironment()Z
    .locals 4
    
    # Check for debugger
    invoke-static {{}}, Landroid/os/Debug;->isDebuggerConnected()Z
    move-result v0
    if-eqz v0, :check_emulator
    const/4 v0, 0x0
    return v0
    
    :check_emulator
    # Check build properties
    const-string v1, "ro.product.model"
    invoke-static {{v1}}, Ljava/lang/System;->getProperty(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v2
    
    if-eqz v2, :environment_ok
    invoke-virtual {{v2}}, Ljava/lang/String;->toLowerCase()Ljava/lang/String;
    move-result-object v2
    const-string v3, "sdk"
    invoke-virtual {{v2, v3}}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z
    move-result v0
    if-eqz v0, :environment_ok
    const/4 v0, 0x0
    return v0
    
    :environment_ok
    const/4 v0, 0x1
    return v0
.end method
"""
        return smali_code
    
    def _derive_layer_key(self, keys: EncryptionKeyPair, layer: int) -> bytes:
        """Derive layer-specific encryption key"""
        layer_input = keys.primary_key + layer.to_bytes(4, 'little') + keys.secondary_key
        return hashlib.sha256(layer_input).digest()[:16]
    
    def _xor_encrypt(self, data: bytes, key: bytes) -> bytes:
        """Enhanced XOR encryption with key stretching"""
        key_stream = self._generate_keystream(key, len(data))
        return bytes(a ^ b for a, b in zip(data, key_stream))
    
    def _aes_like_encrypt(self, data: bytes, key: bytes) -> bytes:
        """AES-like block cipher encryption"""
        block_size = 16
        encrypted = bytearray()
        
        # Pad data
        padded_data = data + b'\x00' * (block_size - len(data) % block_size)
        
        for i in range(0, len(padded_data), block_size):
            block = padded_data[i:i+block_size]
            encrypted_block = self._encrypt_block(block, key)
            encrypted.extend(encrypted_block)
        
        return bytes(encrypted)
    
    def _polyalphabetic_encrypt(self, data: bytes, key: bytes) -> bytes:
        """Polyalphabetic cipher with dynamic key"""
        key_int = int.from_bytes(key[:4], 'little')
        encrypted = bytearray()
        
        for i, byte in enumerate(data):
            key_byte = ((key_int * (i + 1)) % 256) ^ (key[i % len(key)])
            encrypted.append(byte ^ key_byte)
        
        return bytes(encrypted)
    
    def _rc4_like_encrypt(self, data: bytes, key: bytes) -> bytes:
        """RC4-like stream cipher"""
        S = list(range(256))
        j = 0
        
        # Key scheduling
        for i in range(256):
            j = (j + S[i] + key[i % len(key)]) % 256
            S[i], S[j] = S[j], S[i]
        
        # Pseudo-random generation
        i = j = 0
        encrypted = bytearray()
        
        for byte in data:
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            k = S[(S[i] + S[j]) % 256]
            encrypted.append(byte ^ k)
        
        return bytes(encrypted)
    
    def _custom_matrix_encrypt(self, data: bytes, key: bytes) -> bytes:
        """Custom matrix-based encryption"""
        matrix_size = 4
        key_matrix = self._generate_key_matrix(key, matrix_size)
        encrypted = bytearray()
        
        # Process data in chunks
        for i in range(0, len(data), matrix_size):
            chunk = data[i:i+matrix_size]
            if len(chunk) < matrix_size:
                chunk += b'\x00' * (matrix_size - len(chunk))
            
            encrypted_chunk = self._matrix_multiply(chunk, key_matrix)
            encrypted.extend(encrypted_chunk)
        
        return bytes(encrypted)
    
    def _generate_keystream(self, key: bytes, length: int) -> bytes:
        """Generate keystream for XOR encryption"""
        keystream = bytearray()
        key_hash = hashlib.sha256(key).digest()
        
        for i in range(length):
            position_key = (i.to_bytes(4, 'little') + key_hash)
            keystream.append(hashlib.md5(position_key).digest()[0])
        
        return bytes(keystream)
    
    def _encrypt_block(self, block: bytes, key: bytes) -> bytes:
        """Encrypt single block using substitution-permutation network"""
        # Simple S-box substitution
        s_box = self._generate_sbox(key)
        substituted = bytes(s_box[b] for b in block)
        
        # Permutation
        permuted = self._permute_block(substituted, key)
        
        # Key mixing
        key_expanded = (key * (len(permuted) // len(key) + 1))[:len(permuted)]
        mixed = bytes(a ^ b for a, b in zip(permuted, key_expanded))
        
        return mixed
    
    def _generate_sbox(self, key: bytes) -> List[int]:
        """Generate substitution box from key"""
        s_box = list(range(256))
        key_hash = hashlib.sha256(key).digest()
        
        # Shuffle based on key
        for i in range(256):
            j = (i + key_hash[i % len(key_hash)]) % 256
            s_box[i], s_box[j] = s_box[j], s_box[i]
        
        return s_box
    
    def _permute_block(self, block: bytes, key: bytes) -> bytes:
        """Permute block bytes based on key"""
        key_sum = sum(key) % len(block)
        permuted = bytearray(len(block))
        
        for i, byte in enumerate(block):
            new_pos = (i + key_sum) % len(block)
            permuted[new_pos] = byte
        
        return bytes(permuted)
    
    def _generate_key_matrix(self, key: bytes, size: int) -> List[List[int]]:
        """Generate key matrix for matrix encryption"""
        matrix = []
        key_hash = hashlib.sha256(key).digest()
        
        for i in range(size):
            row = []
            for j in range(size):
                idx = (i * size + j) % len(key_hash)
                row.append(key_hash[idx])
            matrix.append(row)
        
        return matrix
    
    def _matrix_multiply(self, data: bytes, matrix: List[List[int]]) -> bytes:
        """Multiply data vector with key matrix"""
        result = bytearray()
        
        for i in range(len(matrix)):
            value = 0
            for j in range(len(data)):
                value += data[j] * matrix[i][j % len(matrix[i])]
            result.append(value % 256)
        
        return bytes(result)
    
    def _generate_key_derivation_smali(self, keys: EncryptionKeyPair) -> str:
        """Generate Smali code for key derivation"""
        
        primary_key_bytes = ', '.join(str(b) for b in keys.primary_key[:16])
        secondary_key_bytes = ', '.join(str(b) for b in keys.secondary_key[:16])
        
        return f"""
# Key derivation method
.method private static deriveKey(I)[B
    .locals 12
    .param p0, "rotation"    # I
    
    # Check cache first
    sget-object v0, Lcom/android/internal/StringDecryptor;->keyCache:Ljava/util/Map;
    invoke-static {{p0}}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v1
    invoke-interface {{v0, v1}}, Ljava/util/Map;->get(Ljava/lang/Object;)Ljava/lang/Object;
    move-result-object v2
    check-cast v2, [B
    
    if-eqz v2, :generate_key
    return-object v2
    
    :generate_key
    # Primary key
    const/16 v3, 0x10
    new-array v4, v3, [B
    {self._generate_array_init_smali(keys.primary_key[:16], 'v4')}
    
    # Secondary key  
    new-array v5, v3, [B
    {self._generate_array_init_smali(keys.secondary_key[:16], 'v5')}
    
    # Apply rotation
    const/16 v6, 0x0
    :rotation_loop
    if-ge v6, v3, :rotation_done
    aget-byte v7, v4, v6
    and-int/lit16 v7, v7, 0xff
    aget-byte v8, v5, v6
    and-int/lit16 v8, v8, 0xff
    add-int v9, v7, v8
    add-int v9, v9, p0
    and-int/lit16 v9, v9, 0xff
    int-to-byte v9, v9
    aput-byte v9, v4, v6
    add-int/lit8 v6, v6, 0x1
    goto :rotation_loop
    
    :rotation_done
    # Cache result
    invoke-interface {{v0, v1, v4}}, Ljava/util/Map;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    return-object v4
.end method"""
    
    def _generate_decryption_algorithm_smali(self, encrypted_data: Dict[str, Any], 
                                           keys: EncryptionKeyPair) -> str:
        """Generate Smali code for decryption algorithm"""
        
        layers = encrypted_data["layers"]
        method_index = encrypted_data["method_index"]
        
        return f"""
# Apply decryption layers
.method private static applyDecryptionLayers([B[B)[B
    .locals 6
    .param p0, "data"    # [B
    .param p1, "key"    # [B
    
    move-object v0, p0
    
    # Apply {len(layers)} decryption layers in reverse
    const/4 v1, {len(layers) - 1}
    :layer_loop
    if-gez v1, :layers_done
    
    # Derive layer key
    invoke-static {{p1, v1}}, Lcom/android/internal/StringDecryptor;->deriveLayerKey([BI)[B
    move-result-object v2
    
    # Apply layer decryption based on method {method_index}
    const/4 v3, {method_index}
    packed-switch v3, :decrypt_switch
    goto :next_layer
    
    :decrypt_switch
    .packed-switch 0x0
        :decrypt_xor
        :decrypt_aes_like
        :decrypt_poly
        :decrypt_rc4_like
        :decrypt_matrix
    .end packed-switch
    
    :decrypt_xor
    invoke-static {{v0, v2}}, Lcom/android/internal/StringDecryptor;->xorDecrypt([B[B)[B
    move-result-object v0
    goto :next_layer
    
    :decrypt_aes_like
    invoke-static {{v0, v2}}, Lcom/android/internal/StringDecryptor;->aesLikeDecrypt([B[B)[B
    move-result-object v0
    goto :next_layer
    
    :decrypt_poly
    invoke-static {{v0, v2}}, Lcom/android/internal/StringDecryptor;->polyDecrypt([B[B)[B
    move-result-object v0
    goto :next_layer
    
    :decrypt_rc4_like
    invoke-static {{v0, v2}}, Lcom/android/internal/StringDecryptor;->rc4LikeDecrypt([B[B)[B
    move-result-object v0
    goto :next_layer
    
    :decrypt_matrix
    invoke-static {{v0, v2}}, Lcom/android/internal/StringDecryptor;->matrixDecrypt([B[B)[B
    move-result-object v0
    
    :next_layer
    add-int/lit8 v1, v1, -0x1
    goto :layer_loop
    
    :layers_done
    return-object v0
.end method

# Individual decryption methods
.method private static xorDecrypt([B[B)[B
    .locals 8
    .param p0, "data"    # [B
    .param p1, "key"    # [B
    
    array-length v0, p0
    new-array v1, v0, [B
    
    const/4 v2, 0x0
    :xor_loop
    if-ge v2, v0, :xor_done
    aget-byte v3, p0, v2
    array-length v4, p1
    rem-int v4, v2, v4
    aget-byte v5, p1, v4
    xor-int v6, v3, v5
    int-to-byte v6, v6
    aput-byte v6, v1, v2
    add-int/lit8 v2, v2, 0x1
    goto :xor_loop
    
    :xor_done
    return-object v1
.end method

# Additional decryption methods would be generated here...
# (aesLikeDecrypt, polyDecrypt, rc4LikeDecrypt, matrixDecrypt)
"""
    
    def _generate_array_init_smali(self, byte_array: bytes, register: str) -> str:
        """Generate Smali code to initialize byte array"""
        instructions = []
        for i, byte_val in enumerate(byte_array):
            instructions.append(f"    const/16 v10, {byte_val}")
            instructions.append(f"    aput-byte v10, {register}, {i}")
        return '\n'.join(instructions)

class ControlFlowFlattening:
    """Advanced control flow obfuscation engine"""
    
    def __init__(self, complexity_level: int = 5):
        self.complexity_level = complexity_level
        self.dispatcher_count = 0
        self.state_machine_count = 0
    
    def flatten_method(self, smali_content: str, method_name: str) -> str:
        """Apply control flow flattening to a specific method"""
        
        # Find method boundaries
        method_pattern = rf'\.method.*{method_name}.*?\n(.*?)\.end method'
        method_match = re.search(method_pattern, smali_content, re.DOTALL)
        
        if not method_match:
            return smali_content
        
        original_body = method_match.group(1)
        
        # Extract basic blocks
        basic_blocks = self._extract_basic_blocks(original_body)
        
        if len(basic_blocks) < 2:
            return smali_content  # Not worth flattening
        
        # Generate flattened control flow
        flattened_body = self._generate_flattened_flow(basic_blocks, method_name)
        
        # Replace original method body
        new_content = smali_content.replace(method_match.group(0), 
                                           method_match.group(0).replace(original_body, flattened_body))
        
        return new_content
    
    def _extract_basic_blocks(self, method_body: str) -> List[Dict[str, Any]]:
        """Extract basic blocks from method body"""
        lines = method_body.strip().split('\n')
        blocks = []
        current_block = []
        block_id = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            current_block.append(line)
            
            # Check for block terminators
            if (stripped.startswith(('goto', 'if-', 'return', 'throw')) or
                stripped.startswith(':') and current_block and len(current_block) > 1):
                
                if current_block:
                    blocks.append({
                        'id': block_id,
                        'code': current_block[:-1] if stripped.startswith(':') else current_block,
                        'terminator': stripped if not stripped.startswith(':') else None,
                        'label': stripped if stripped.startswith(':') else None
                    })
                    block_id += 1
                    current_block = [line] if stripped.startswith(':') else []
        
        # Add remaining code as final block
        if current_block:
            blocks.append({
                'id': block_id,
                'code': current_block,
                'terminator': None,
                'label': None
            })
        
        return blocks
    
    def _generate_flattened_flow(self, blocks: List[Dict[str, Any]], method_name: str) -> str:
        """Generate flattened control flow using dispatcher pattern"""
        
        dispatcher_name = f"dispatcher_{self.dispatcher_count}_{method_name}"
        self.dispatcher_count += 1
        
        # Generate state variables
        state_var = f"v_state_{random.randint(1000, 9999)}"
        next_state_var = f"v_next_{random.randint(1000, 9999)}"
        
        # Create state mapping
        state_mapping = {}
        for i, block in enumerate(blocks):
            # Use non-sequential state numbers for obfuscation
            state_mapping[i] = random.randint(1000, 9999) + i * 17
        
        flattened_code = f"""
    # Control flow flattening - dispatcher pattern
    const/4 {state_var}, {state_mapping[0]}  # Initial state
    
    :{dispatcher_name}_loop
    packed-switch {state_var}, :{dispatcher_name}_switch
    goto :{dispatcher_name}_end
    
    :{dispatcher_name}_switch
    .packed-switch {min(state_mapping.values())}
"""
        
        # Generate switch table
        sorted_states = sorted(state_mapping.values())
        for state in sorted_states:
            # Find corresponding block
            block_id = None
            for bid, bstate in state_mapping.items():
                if bstate == state:
                    block_id = bid
                    break
            
            if block_id is not None:
                flattened_code += f"        :{dispatcher_name}_block_{block_id}\n"
            else:
                flattened_code += f"        :{dispatcher_name}_default\n"
        
        flattened_code += "    .end packed-switch\n\n"
        
        # Generate block implementations
        for i, block in enumerate(blocks):
            state = state_mapping[i]
            flattened_code += f"    :{dispatcher_name}_block_{i}\n"
            
            # Add block code
            for line in block['code']:
                flattened_code += f"    {line.strip()}\n"
            
            # Add state transition logic
            next_block = (i + 1) % len(blocks)
            if i < len(blocks) - 1:
                next_state = state_mapping[next_block]
                flattened_code += f"    const/4 {state_var}, {next_state}\n"
                flattened_code += f"    goto :{dispatcher_name}_loop\n\n"
            else:
                flattened_code += f"    goto :{dispatcher_name}_end\n\n"
        
        # Add dummy blocks for confusion
        for dummy_id in range(self.complexity_level):
            flattened_code += f"""    :{dispatcher_name}_dummy_{dummy_id}
    # Dummy block for confusion
    invoke-static {{}}, Ljava/lang/System;->currentTimeMillis()J
    move-result-wide v99
    const-wide/16 v98, 0x0
    cmp-long v97, v99, v98
    if-lez v97, :{dispatcher_name}_end
    goto :{dispatcher_name}_end

"""
        
        flattened_code += f"    :{dispatcher_name}_end\n"
        
        return flattened_code
    
    def create_opaque_predicates(self, count: int = 5) -> List[str]:
        """Create opaque predicates for control flow obfuscation"""
        predicates = []
        
        predicate_templates = [
            # Mathematical predicates
            "invoke-static {}, Ljava/lang/System;->currentTimeMillis()J\n"
            "move-result-wide v{reg1}\n"
            "const-wide/16 v{reg2}, 0x2\n"
            "rem-long v{reg3}, v{reg1}, v{reg2}\n"
            "const-wide/16 v{reg4}, 0x0\n"
            "cmp-long v{reg5}, v{reg3}, v{reg4}\n"
            "if-gez v{reg5}, :opaque_true_{id}",
            
            # String length predicates
            "const-string v{reg1}, \"{random_string}\"\n"
            "invoke-virtual {{v{reg1}}}, Ljava/lang/String;->length()I\n"
            "move-result v{reg2}\n"
            "const/4 v{reg3}, {expected_length}\n"
            "if-ne v{reg2}, v{reg3}, :opaque_true_{id}",
            
            # Hash-based predicates
            "const-string v{reg1}, \"{hash_input}\"\n"
            "invoke-virtual {{v{reg1}}}, Ljava/lang/String;->hashCode()I\n"
            "move-result v{reg2}\n"
            "const v{reg3}, {expected_hash}\n"
            "if-eq v{reg2}, v{reg3}, :opaque_true_{id}"
        ]
        
        for i in range(count):
            template = random.choice(predicate_templates)
            
            # Generate random values
            random_string = ''.join(random.choices(string.ascii_letters, k=10))
            hash_input = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            expected_hash = hash(hash_input) & 0x7FFFFFFF
            
            predicate = template.format(
                id=i,
                reg1=random.randint(10, 20),
                reg2=random.randint(21, 30),
                reg3=random.randint(31, 40),
                reg4=random.randint(41, 50),
                reg5=random.randint(51, 60),
                random_string=random_string,
                expected_length=len(random_string),
                hash_input=hash_input,
                expected_hash=expected_hash
            )
            
            predicates.append(predicate)
        
        return predicates

class AdvancedDeadCodeInjection:
    """Advanced dead code injection with realistic patterns"""
    
    def __init__(self, injection_ratio: float = 0.3):
        self.injection_ratio = injection_ratio
        self.code_templates = self._load_code_templates()
    
    def inject_dead_code(self, smali_content: str) -> str:
        """Inject sophisticated dead code throughout the Smali file"""
        
        lines = smali_content.split('\n')
        modified_lines = []
        
        in_method = False
        method_line_count = 0
        
        for line in lines:
            modified_lines.append(line)
            
            # Track method boundaries
            if '.method' in line:
                in_method = True
                method_line_count = 0
            elif '.end method' in line:
                in_method = False
                method_line_count = 0
            elif in_method:
                method_line_count += 1
                
                # Inject dead code probabilistically
                if (method_line_count > 3 and 
                    random.random() < self.injection_ratio and
                    not line.strip().startswith((':', '#', '.', 'goto', 'return'))):
                    
                    dead_code = self._generate_dead_code_block()
                    modified_lines.extend(dead_code.split('\n'))
        
        return '\n'.join(modified_lines)
    
    def _generate_dead_code_block(self) -> str:
        """Generate a sophisticated dead code block"""
        
        block_types = [
            self._generate_computation_block,
            self._generate_string_manipulation_block,
            self._generate_collection_operations_block,
            self._generate_reflection_block,
            self._generate_file_system_block,
            self._generate_crypto_operations_block
        ]
        
        generator = random.choice(block_types)
        return generator()
    
    def _generate_computation_block(self) -> str:
        """Generate mathematical computation dead code"""
        reg_base = random.randint(70, 90)
        
        return f"""
    # Dead code: Complex mathematical computation
    invoke-static {{}}, Ljava/lang/System;->nanoTime()J
    move-result-wide v{reg_base}
    const-wide/16 v{reg_base+2}, 0x7b
    add-long v{reg_base+4}, v{reg_base}, v{reg_base+2}
    const-wide/16 v{reg_base+6}, 0x3
    div-long v{reg_base+8}, v{reg_base+4}, v{reg_base+6}
    invoke-static {{v{reg_base+8}, v{reg_base+8}}}, Ljava/lang/Math;->max(JJ)J
    move-result-wide v{reg_base+10}
    # Result ignored - dead code
"""
    
    def _generate_string_manipulation_block(self) -> str:
        """Generate string manipulation dead code"""
        reg_base = random.randint(70, 90)
        dummy_string = ''.join(random.choices(string.ascii_letters + string.digits, k=15))
        
        return f"""
    # Dead code: String manipulation
    const-string v{reg_base}, "{dummy_string}"
    invoke-virtual {{v{reg_base}}}, Ljava/lang/String;->length()I
    move-result v{reg_base+1}
    const/4 v{reg_base+2}, 0x0
    const/4 v{reg_base+3}, 0x5
    invoke-virtual {{v{reg_base}, v{reg_base+2}, v{reg_base+3}}}, Ljava/lang/String;->substring(II)Ljava/lang/String;
    move-result-object v{reg_base+4}
    invoke-virtual {{v{reg_base+4}}}, Ljava/lang/String;->toUpperCase()Ljava/lang/String;
    move-result-object v{reg_base+5}
    # Result ignored - dead code
"""
    
    def _generate_collection_operations_block(self) -> str:
        """Generate collection operations dead code"""
        reg_base = random.randint(70, 90)
        
        return f"""
    # Dead code: Collection operations
    new-instance v{reg_base}, Ljava/util/ArrayList;
    invoke-direct {{v{reg_base}}}, Ljava/util/ArrayList;-><init>()V
    const-string v{reg_base+1}, "dummy_item_1"
    invoke-interface {{v{reg_base}, v{reg_base+1}}}, Ljava/util/List;->add(Ljava/lang/Object;)Z
    const-string v{reg_base+2}, "dummy_item_2"
    invoke-interface {{v{reg_base}, v{reg_base+2}}}, Ljava/util/List;->add(Ljava/lang/Object;)Z
    invoke-interface {{v{reg_base}}}, Ljava/util/List;->size()I
    move-result v{reg_base+3}
    invoke-interface {{v{reg_base}}}, Ljava/util/List;->clear()V
    # Collection discarded - dead code
"""
    
    def _generate_reflection_block(self) -> str:
        """Generate reflection-based dead code"""
        reg_base = random.randint(70, 90)
        
        return f"""
    # Dead code: Reflection operations
    :try_start_reflection_{reg_base}
    const-string v{reg_base}, "java.lang.String"
    invoke-static {{v{reg_base}}}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;
    move-result-object v{reg_base+1}
    invoke-virtual {{v{reg_base+1}}}, Ljava/lang/Class;->getMethods()[Ljava/lang/reflect/Method;
    move-result-object v{reg_base+2}
    array-length v{reg_base+3}, v{reg_base+2}
    :try_end_reflection_{reg_base}
    .catch Ljava/lang/Exception; {{:catch_reflection_{reg_base}}}
    goto :end_reflection_{reg_base}
    
    :catch_reflection_{reg_base}
    move-exception v{reg_base+4}
    
    :end_reflection_{reg_base}
    # Reflection result ignored - dead code
"""
    
    def _generate_file_system_block(self) -> str:
        """Generate file system operations dead code"""
        reg_base = random.randint(70, 90)
        temp_filename = f"temp_{random.randint(1000, 9999)}.tmp"
        
        return f"""
    # Dead code: File system operations  
    :try_start_file_{reg_base}
    new-instance v{reg_base}, Ljava/io/File;
    const-string v{reg_base+1}, "/data/local/tmp/{temp_filename}"
    invoke-direct {{v{reg_base}, v{reg_base+1}}}, Ljava/io/File;-><init>(Ljava/lang/String;)V
    invoke-virtual {{v{reg_base}}}, Ljava/io/File;->exists()Z
    move-result v{reg_base+2}
    invoke-virtual {{v{reg_base}}}, Ljava/io/File;->canRead()Z
    move-result v{reg_base+3}
    invoke-virtual {{v{reg_base}}}, Ljava/io/File;->length()J
    move-result-wide v{reg_base+4}
    :try_end_file_{reg_base}
    .catch Ljava/lang/Exception; {{:catch_file_{reg_base}}}
    goto :end_file_{reg_base}
    
    :catch_file_{reg_base}
    move-exception v{reg_base+6}
    
    :end_file_{reg_base}
    # File operations ignored - dead code
"""
    
    def _generate_crypto_operations_block(self) -> str:
        """Generate cryptographic operations dead code"""
        reg_base = random.randint(70, 90)
        
        return f"""
    # Dead code: Cryptographic operations
    :try_start_crypto_{reg_base}
    const-string v{reg_base}, "SHA-256"
    invoke-static {{v{reg_base}}}, Ljava/security/MessageDigest;->getInstance(Ljava/lang/String;)Ljava/security/MessageDigest;
    move-result-object v{reg_base+1}
    const-string v{reg_base+2}, "dummy_data_for_hashing"
    invoke-virtual {{v{reg_base+2}}}, Ljava/lang/String;->getBytes()[B
    move-result-object v{reg_base+3}
    invoke-virtual {{v{reg_base+1}, v{reg_base+3}}}, Ljava/security/MessageDigest;->digest([B)[B
    move-result-object v{reg_base+4}
    array-length v{reg_base+5}, v{reg_base+4}
    :try_end_crypto_{reg_base}
    .catch Ljava/lang/Exception; {{:catch_crypto_{reg_base}}}
    goto :end_crypto_{reg_base}
    
    :catch_crypto_{reg_base}
    move-exception v{reg_base+6}
    
    :end_crypto_{reg_base}
    # Crypto result ignored - dead code
"""
    
    def _load_code_templates(self) -> List[str]:
        """Load realistic code templates for dead code generation"""
        return [
            "invoke-static {}, Ljava/lang/System;->gc()V",
            "invoke-static {}, Ljava/lang/Thread;->yield()V",
            "invoke-static {}, Ljava/lang/System;->currentTimeMillis()J\nmove-result-wide v99",
            "new-instance v98, Ljava/util/Random;\ninvoke-direct {v98}, Ljava/util/Random;-><init>()V"
        ]

class APICallRedirection:
    """Advanced API call redirection and hooking"""
    
    def __init__(self, redirection_level: int = 2):
        self.redirection_level = redirection_level
        self.hook_counter = 0
        self.api_mappings = self._initialize_api_mappings()
    
    def redirect_api_calls(self, smali_content: str) -> str:
        """Redirect sensitive API calls through proxy methods"""
        
        modified_content = smali_content
        
        # Find and redirect API calls
        for original_api, proxy_info in self.api_mappings.items():
            if self.redirection_level >= proxy_info['min_level']:
                modified_content = self._redirect_api_call(modified_content, original_api, proxy_info)
        
        # Add proxy methods at the end of the class
        proxy_methods = self._generate_proxy_methods()
        
        # Insert before the last line (usually closing)
        lines = modified_content.split('\n')
        lines.insert(-1, proxy_methods)
        
        return '\n'.join(lines)
    
    def _initialize_api_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Initialize API redirection mappings"""
        return {
            # Network APIs
            'Ljava/net/URL;->openConnection()Ljava/net/URLConnection;': {
                'proxy_method': 'openConnectionProxy',
                'min_level': 1,
                'return_type': 'Ljava/net/URLConnection;',
                'parameters': []
            },
            
            # File System APIs
            'Ljava/io/File;->exists()Z': {
                'proxy_method': 'fileExistsProxy',
                'min_level': 1,
                'return_type': 'Z',
                'parameters': ['Ljava/io/File;']
            },
            
            # System APIs
            'Ljava/lang/Runtime;->exec(Ljava/lang/String;)Ljava/lang/Process;': {
                'proxy_method': 'runtimeExecProxy',
                'min_level': 2,
                'return_type': 'Ljava/lang/Process;',
                'parameters': ['Ljava/lang/String;']
            },
            
            # Telephony APIs
            'Landroid/telephony/TelephonyManager;->getDeviceId()Ljava/lang/String;': {
                'proxy_method': 'getDeviceIdProxy',
                'min_level': 2,
                'return_type': 'Ljava/lang/String;',
                'parameters': []
            },
            
            # Location APIs
            'Landroid/location/LocationManager;->getLastKnownLocation(Ljava/lang/String;)Landroid/location/Location;': {
                'proxy_method': 'getLocationProxy',
                'min_level': 3,
                'return_type': 'Landroid/location/Location;',
                'parameters': ['Ljava/lang/String;']
            }
        }
    
    def _redirect_api_call(self, content: str, original_api: str, proxy_info: Dict[str, Any]) -> str:
        """Redirect specific API call to proxy method"""
        
        # Find invoke patterns
        invoke_patterns = [
            f'invoke-virtual {{([^}}]+)}}, {re.escape(original_api)}',
            f'invoke-static {{([^}}]+)}}, {re.escape(original_api)}',
            f'invoke-interface {{([^}}]+)}}, {re.escape(original_api)}'
        ]
        
        for pattern in invoke_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                original_call = match.group(0)
                registers = match.group(1)
                
                # Generate proxy call
                proxy_call = self._generate_proxy_call(registers, proxy_info, original_call)
                content = content.replace(original_call, proxy_call)
        
        return content
    
    def _generate_proxy_call(self, registers: str, proxy_info: Dict[str, Any], original_call: str) -> str:
        """Generate proxy method call"""
        
        proxy_method = proxy_info['proxy_method']
        return_type = proxy_info['return_type']
        
        # Preserve original behavior but add indirection
        proxy_call = f"""# API redirection - {proxy_method}
    invoke-static {{{registers}}}, Lcom/android/internal/APIProxy;->{proxy_method}({';'.join(proxy_info['parameters'])}){return_type}"""
        
        return proxy_call
    
    def _generate_proxy_methods(self) -> str:
        """Generate all proxy methods"""
        
        proxy_class = f"""
# API Proxy Class for Call Redirection
.class public Lcom/android/internal/APIProxy;
.super Ljava/lang/Object;

# Static initialization
.method static constructor <clinit>()V
    .locals 0
    # Initialize proxy hooks
    invoke-static {{}}, Lcom/android/internal/APIProxy;->initializeHooks()V
    return-void
.end method

# Hook initialization
.method private static initializeHooks()V
    .locals 2
    
    # Anti-analysis check
    invoke-static {{}}, Lcom/android/internal/APIProxy;->checkAnalysisEnvironment()Z
    move-result v0
    if-nez v0, :init_hooks
    return-void
    
    :init_hooks
    # Initialize hook state
    const/4 v1, 0x1
    sput-boolean v1, Lcom/android/internal/APIProxy;->hooksInitialized:Z
    return-void
.end method

# Environment check
.method private static checkAnalysisEnvironment()Z
    .locals 3
    
    # Check for debugging
    invoke-static {{}}, Landroid/os/Debug;->isDebuggerConnected()Z
    move-result v0
    if-eqz v0, :check_emulator
    const/4 v0, 0x0
    return v0
    
    :check_emulator
    # Check for emulator
    const-string v1, "ro.product.model"
    invoke-static {{v1}}, Ljava/lang/System;->getProperty(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v2
    
    if-eqz v2, :environment_ok
    const-string v1, "sdk"
    invoke-virtual {{v2, v1}}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z
    move-result v0
    if-eqz v0, :environment_ok
    const/4 v0, 0x0
    return v0
    
    :environment_ok
    const/4 v0, 0x1
    return v0
.end method

# Network Connection Proxy
.method public static openConnectionProxy(Ljava/net/URL;)Ljava/net/URLConnection;
    .locals 4
    .param p0, "url"    # Ljava/net/URL;
    
    # Log connection attempt
    const-string v0, "APIProxy"
    const-string v1, "Network connection requested"
    invoke-static {{v0, v1}}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    
    # Apply connection filtering/modification
    invoke-static {{p0}}, Lcom/android/internal/APIProxy;->filterNetworkRequest(Ljava/net/URL;)Ljava/net/URL;
    move-result-object v2
    
    # Proceed with original call
    :try_start_connection
    invoke-virtual {{v2}}, Ljava/net/URL;->openConnection()Ljava/net/URLConnection;
    move-result-object v3
    return-object v3
    :try_end_connection
    .catch Ljava/lang/Exception; {{:connection_error}}
    
    :connection_error
    move-exception v3
    const/4 v0, 0x0
    return-object v0
.end method

# File System Proxy
.method public static fileExistsProxy(Ljava/io/File;)Z
    .locals 3
    .param p0, "file"    # Ljava/io/File;
    
    # Check for sensitive file access
    invoke-virtual {{p0}}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;
    move-result-object v0
    
    # Filter sensitive paths
    invoke-static {{v0}}, Lcom/android/internal/APIProxy;->isSensitivePath(Ljava/lang/String;)Z
    move-result v1
    if-eqz v1, :proceed_check
    
    # Return false for sensitive files to avoid detection
    const/4 v0, 0x0
    return v0
    
    :proceed_check
    # Proceed with original check
    invoke-virtual {{p0}}, Ljava/io/File;->exists()Z
    move-result v2
    return v2
.end method

# Runtime Execution Proxy
.method public static runtimeExecProxy(Ljava/lang/String;)Ljava/lang/Process;
    .locals 4
    .param p0, "command"    # Ljava/lang/String;
    
    # Log execution attempt
    const-string v0, "APIProxy"
    const-string v1, "Runtime execution requested"
    invoke-static {{v0, v1}}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    
    # Filter and modify command
    invoke-static {{p0}}, Lcom/android/internal/APIProxy;->filterCommand(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v2
    
    # Execute with stealth
    :try_start_exec
    invoke-static {{}}, Ljava/lang/Runtime;->getRuntime()Ljava/lang/Runtime;
    move-result-object v3
    invoke-virtual {{v3, v2}}, Ljava/lang/Runtime;->exec(Ljava/lang/String;)Ljava/lang/Process;
    move-result-object v0
    return-object v0
    :try_end_exec
    .catch Ljava/lang/Exception; {{:exec_error}}
    
    :exec_error
    move-exception v0
    const/4 v0, 0x0
    return-object v0
.end method

# Device ID Proxy
.method public static getDeviceIdProxy(Landroid/telephony/TelephonyManager;)Ljava/lang/String;
    .locals 3
    .param p0, "telephonyManager"    # Landroid/telephony/TelephonyManager;
    
    # Check analysis environment
    invoke-static {{}}, Lcom/android/internal/APIProxy;->checkAnalysisEnvironment()Z
    move-result v0
    if-nez v0, :get_real_id
    
    # Return fake ID in analysis environment
    const-string v1, "000000000000000"
    return-object v1
    
    :get_real_id
    # Get real device ID
    :try_start_device_id
    invoke-virtual {{p0}}, Landroid/telephony/TelephonyManager;->getDeviceId()Ljava/lang/String;
    move-result-object v2
    return-object v2
    :try_end_device_id
    .catch Ljava/lang/Exception; {{:device_id_error}}
    
    :device_id_error
    move-exception v0
    const-string v1, "unknown"
    return-object v1
.end method

# Helper methods
.method private static filterNetworkRequest(Ljava/net/URL;)Ljava/net/URL;
    .locals 1
    .param p0, "url"    # Ljava/net/URL;
    
    # Apply network filtering logic
    # For now, return original URL
    return-object p0
.end method

.method private static isSensitivePath(Ljava/lang/String;)Z
    .locals 3
    .param p0, "path"    # Ljava/lang/String;
    
    # Check for root detection paths
    const-string v0, "/system/bin/su"
    invoke-virtual {{p0, v0}}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z
    move-result v1
    if-eqz v1, :check_xposed
    const/4 v0, 0x1
    return v0
    
    :check_xposed
    const-string v0, "xposed"
    invoke-virtual {{p0, v0}}, Ljava/lang/String;->toLowerCase()Ljava/lang/String;
    move-result-object v2
    invoke-virtual {{v2, v0}}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z
    move-result v1
    return v1
.end method

.method private static filterCommand(Ljava/lang/String;)Ljava/lang/String;
    .locals 1
    .param p0, "command"    # Ljava/lang/String;
    
    # Apply command filtering
    # For now, return original command
    return-object p0
.end method

# Static fields
.field private static hooksInitialized:Z
"""
        
        return proxy_class

class AdvancedObfuscationEngine:
    """Main advanced obfuscation engine coordinating all techniques"""
    
    def __init__(self, config: ObfuscationConfig):
        self.config = config
        self.string_encryptor = DynamicStringEncryption(config.string_encryption_level)
        self.flow_flattener = ControlFlowFlattening(config.control_flow_complexity)
        self.dead_code_injector = AdvancedDeadCodeInjection(config.dead_code_ratio)
        self.api_redirector = APICallRedirection(config.api_redirection_level)
        
    def apply_full_obfuscation(self, apk_path: Path, output_path: Path) -> bool:
        """Apply comprehensive advanced obfuscation to APK"""
        
        try:
            # Create workspace
            workspace = apk_path.parent / f"obfuscation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            workspace.mkdir(exist_ok=True)
            
            # Extract APK
            extract_dir = workspace / "extracted"
            self._extract_apk(apk_path, extract_dir)
            
            # Apply obfuscation techniques
            self._apply_string_encryption(extract_dir)
            self._apply_control_flow_flattening(extract_dir)
            self._apply_dead_code_injection(extract_dir)
            self._apply_api_redirection(extract_dir)
            
            # Recompile and sign
            success = self._recompile_and_sign(extract_dir, output_path)
            
            # Cleanup
            if success:
                shutil.rmtree(workspace, ignore_errors=True)
            
            return success
            
        except Exception as e:
            print(f"Advanced obfuscation failed: {e}")
            return False
    
    def _extract_apk(self, apk_path: Path, extract_dir: Path):
        """Extract APK for modification"""
        apktool_path = "/workspace/tools/apktool/apktool.jar"
        
        cmd = [
            "java", "-jar", apktool_path, "d",
            str(apk_path), "-o", str(extract_dir), "-f"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise Exception(f"APK extraction failed: {result.stderr}")
    
    def _apply_string_encryption(self, extract_dir: Path):
        """Apply advanced string encryption"""
        
        smali_dirs = [d for d in extract_dir.iterdir() if d.name.startswith("smali")]
        
        # Generate dynamic keys
        keys = self.string_encryptor.generate_dynamic_keys()
        
        for smali_dir in smali_dirs:
            for smali_file in smali_dir.rglob("*.smali"):
                try:
                    content = smali_file.read_text()
                    
                    # Find and encrypt strings
                    modified_content = self._encrypt_strings_in_file(content, keys)
                    
                    smali_file.write_text(modified_content)
                    
                except Exception as e:
                    print(f"String encryption error in {smali_file}: {e}")
        
        # Add decryption class
        if smali_dirs:
            decryption_class = self.string_encryptor.generate_decryption_smali({}, keys)
            decryption_file = smali_dirs[0] / "com" / "android" / "internal" / "StringDecryptor.smali"
            decryption_file.parent.mkdir(parents=True, exist_ok=True)
            decryption_file.write_text(decryption_class)
    
    def _apply_control_flow_flattening(self, extract_dir: Path):
        """Apply control flow flattening"""
        
        smali_dirs = [d for d in extract_dir.iterdir() if d.name.startswith("smali")]
        
        for smali_dir in smali_dirs:
            for smali_file in smali_dir.rglob("*.smali"):
                try:
                    content = smali_file.read_text()
                    
                    # Apply flattening to significant methods
                    methods = self._extract_method_names(content)
                    for method in methods:
                        if len(method) > 5:  # Only flatten substantial methods
                            content = self.flow_flattener.flatten_method(content, method)
                    
                    smali_file.write_text(content)
                    
                except Exception as e:
                    print(f"Control flow flattening error in {smali_file}: {e}")
    
    def _apply_dead_code_injection(self, extract_dir: Path):
        """Apply advanced dead code injection"""
        
        smali_dirs = [d for d in extract_dir.iterdir() if d.name.startswith("smali")]
        
        for smali_dir in smali_dirs:
            for smali_file in smali_dir.rglob("*.smali"):
                try:
                    content = smali_file.read_text()
                    modified_content = self.dead_code_injector.inject_dead_code(content)
                    smali_file.write_text(modified_content)
                    
                except Exception as e:
                    print(f"Dead code injection error in {smali_file}: {e}")
    
    def _apply_api_redirection(self, extract_dir: Path):
        """Apply API call redirection"""
        
        smali_dirs = [d for d in extract_dir.iterdir() if d.name.startswith("smali")]
        
        for smali_dir in smali_dirs:
            for smali_file in smali_dir.rglob("*.smali"):
                try:
                    content = smali_file.read_text()
                    modified_content = self.api_redirector.redirect_api_calls(content)
                    smali_file.write_text(modified_content)
                    
                except Exception as e:
                    print(f"API redirection error in {smali_file}: {e}")
    
    def _encrypt_strings_in_file(self, content: str, keys: EncryptionKeyPair) -> str:
        """Encrypt strings in Smali file content"""
        
        # Find string constants
        string_pattern = r'const-string\s+(v\d+),\s*"([^"]*)"'
        
        def replace_string(match):
            register = match.group(1)
            original_string = match.group(2)
            
            # Skip very short strings
            if len(original_string) < 4:
                return match.group(0)
            
            # Encrypt string
            encrypted_data = self.string_encryptor.encrypt_string(original_string, keys)
            
            # Generate decryption call
            return f"""const-string {register}, "{encrypted_data['encrypted']}"
    const/4 v99, {encrypted_data['key_rotation']}
    invoke-static {{{register}, v99}}, Lcom/android/internal/StringDecryptor;->decrypt(Ljava/lang/String;I)Ljava/lang/String;
    move-result-object {register}"""
        
        return re.sub(string_pattern, replace_string, content)
    
    def _extract_method_names(self, content: str) -> List[str]:
        """Extract method names from Smali content"""
        method_pattern = r'\.method.*?(\w+)\('
        matches = re.findall(method_pattern, content)
        return [match for match in matches if not match.startswith('<')]
    
    def _recompile_and_sign(self, extract_dir: Path, output_path: Path) -> bool:
        """Recompile and sign the obfuscated APK"""
        
        apktool_path = "/workspace/tools/apktool/apktool.jar"
        
        # Recompile
        cmd = [
            "java", "-jar", apktool_path, "b",
            str(extract_dir), "-o", str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            # Sign the APK
            return self._sign_apk(output_path)
        else:
            print(f"Recompilation failed: {result.stderr}")
            return False
    
    def _sign_apk(self, apk_path: Path) -> bool:
        """Sign APK with debug keystore"""
        
        try:
            debug_keystore = "/workspace/debug.keystore"
            
            # Create debug keystore if it doesn't exist
            if not Path(debug_keystore).exists():
                subprocess.run([
                    "keytool", "-genkey", "-v", "-keystore", debug_keystore,
                    "-alias", "androiddebugkey", "-keyalg", "RSA", "-keysize", "2048",
                    "-validity", "10000", "-keypass", "android", "-storepass", "android",
                    "-dname", "CN=Android Debug,O=Android,C=US"
                ], check=True, capture_output=True)
            
            # Sign APK
            subprocess.run([
                "jarsigner", "-verbose", "-sigalg", "SHA1withRSA", "-digestalg", "SHA1",
                "-keystore", debug_keystore, "-storepass", "android",
                "-keypass", "android", str(apk_path), "androiddebugkey"
            ], check=True, capture_output=True)
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"APK signing failed: {e}")
            return False

# Export main classes
__all__ = [
    'AdvancedObfuscationEngine', 'DynamicStringEncryption', 'ControlFlowFlattening',
    'AdvancedDeadCodeInjection', 'APICallRedirection', 'ObfuscationConfig', 'EncryptionKeyPair'
]