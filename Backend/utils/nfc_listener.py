#!/usr/bin/env python3
"""
NFC Card Listener with Background Monitoring and Callback Support

Based on pyscard wrapper samples from https://pyscard.sourceforge.io/pyscard-wrapper.html
This implementation provides a background service that monitors NFC card changes
and executes user-defined callbacks when cards are inserted or removed.

Features:
- Background monitoring using threading
- Configurable callbacks for card insertion/removal
- Access to card ATR and reader information
- Graceful shutdown handling
- Error recovery and reconnection
"""

import threading
import time
import sys
from typing import Callable, Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

import smartcard.util
from smartcard.scard import *
from smartcard.System import readers
import ndef

class CardEvent(Enum):
    """Enumeration of card events"""
    INSERTED = "inserted"
    REMOVED = "removed"
    CHANGED = "changed"


@dataclass
class CardInfo:
    """Information about a detected card"""
    reader_name: str
    atr: List[int]
    atr_hex: str
    event_state: int
    event_type: CardEvent
    timestamp: float


class NFCListener:
    """
    Background NFC card listener with callback support
    
    Usage:
        def on_card_event(card_info: CardInfo):
            print(f"Card {card_info.event_type.value} in {card_info.reader_name}")
            print(f"ATR: {card_info.atr_hex}")
        
        listener = NFCListener(callback=on_card_event)
        listener.start()
        
        # Do other work...
        time.sleep(30)
        
        listener.stop()
    """
    
    def __init__(self, 
                 handle_valid_tag_id: Optional[Callable[[int, CardInfo], None]] = None,
                 handle_invalid_tag_id: Optional[Callable[[CardInfo], None]] = None,
                 poll_interval: float = 1.0,
                 timeout_ms: int = 1000):
        """
        Initialize the NFC listener
        
        Args:
            callback: Function to call when card events occur
            poll_interval: Time between polls when no events occur (seconds)
            timeout_ms: Timeout for card status changes (milliseconds)
        """
        self.handle_valid_tag_id = handle_valid_tag_id
        self.handle_invalid_tag_id = handle_invalid_tag_id
        self.poll_interval = poll_interval
        self.timeout_ms = timeout_ms
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._hcontext: Optional[int] = None
        self._readers: List[str] = []
        self._current_states: List[Tuple] = []
        
    def set_callback(self, callback: Callable[[CardInfo], None]):
        """Set or update the callback function"""
        self.callback = callback
    
    def start(self) -> bool:
        """
        Start the background monitoring thread
        
        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            print("Listener is already running")
            return False
            
        try:
            # Establish PCSC context
            hresult, self._hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
            if hresult != SCARD_S_SUCCESS:
                raise Exception(f"Failed to establish context: {SCardGetErrorMessage(hresult)}")
            
            # Get list of readers
            hresult, self._readers = SCardListReaders(self._hcontext, [])
            if hresult != SCARD_S_SUCCESS:
                raise Exception(f"Failed to list readers: {SCardGetErrorMessage(hresult)}")
            
            if len(self._readers) < 1:
                raise Exception("No smart card readers found")
            
            print(f"Found {len(self._readers)} reader(s): {self._readers}")
            
            # Initialize reader states
            self._current_states = []
            for reader in self._readers:
                self._current_states.append((reader, SCARD_STATE_UNAWARE))
            
            # Get initial states
            hresult, self._current_states = SCardGetStatusChange(
                self._hcontext, 0, self._current_states
            )
            if hresult != SCARD_S_SUCCESS:
                print(f"Warning: Could not get initial states: {SCardGetErrorMessage(hresult)}")
            
            # Start monitoring thread
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            
            print("NFC listener started successfully")
            return True
            
        except Exception as e:
            print(f"Failed to start NFC listener: {e}")
            self._cleanup()
            return False
    
    def stop(self):
        """Stop the background monitoring"""
        if not self._running:
            return
            
        print("Stopping NFC listener...")
        self._running = False
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        self._cleanup()
        print("NFC listener stopped")
    
    def is_running(self) -> bool:
        """Check if the listener is currently running"""
        return self._running
    
    def get_readers(self) -> List[str]:
        """Get list of available readers"""
        return self._readers.copy()
    
    def _cleanup(self):
        """Clean up PCSC resources"""
        if self._hcontext:
            try:
                hresult = SCardReleaseContext(self._hcontext)
                if hresult != SCARD_S_SUCCESS:
                    print(f"Warning: Failed to release context: {SCardGetErrorMessage(hresult)}")
            except:
                pass
            finally:
                self._hcontext = None
    
    def _monitor_loop(self):
        """Main monitoring loop running in background thread"""
        print("Starting card monitoring loop...")
        
        while self._running:
            try:
                # Wait for state changes
                hresult, new_states = SCardGetStatusChange(
                    self._hcontext, self.timeout_ms, self._current_states
                )
                
                if not self._running:
                    break
                
                if hresult == SCARD_E_TIMEOUT:
                    # No changes, continue monitoring
                    continue
                elif hresult != SCARD_S_SUCCESS:
                    print(f"Error in status change: {SCardGetErrorMessage(hresult)}")
                    time.sleep(self.poll_interval)
                    continue
                
                # Process state changes
                for i, (reader, new_state, atr) in enumerate(new_states):
                    old_reader, old_state = self._current_states[i][:2]
                    
                    if new_state & SCARD_STATE_CHANGED:
                        self._handle_state_change(reader, old_state, new_state, atr)
                
                # Update current states for next iteration
                self._current_states = new_states
                
            except Exception as e:
                if self._running:
                    print(f"Error in monitoring loop: {e}")
                    time.sleep(self.poll_interval)
    
    def _handle_state_change(self, reader: str, old_state: int, new_state: int, atr: List[int]):
        """Handle a detected state change"""
        try:
            # Determine event type
            event_type = None
            
            if (new_state & SCARD_STATE_PRESENT) and not (old_state & SCARD_STATE_PRESENT):
                event_type = CardEvent.INSERTED
            elif not (new_state & SCARD_STATE_PRESENT) and (old_state & SCARD_STATE_PRESENT):
                event_type = CardEvent.REMOVED
            elif (new_state & SCARD_STATE_PRESENT) and (old_state & SCARD_STATE_PRESENT):
                # Card was present and still is, but ATR might have changed
                event_type = CardEvent.CHANGED
            
            if event_type and self.handle_valid_tag_id and self.handle_invalid_tag_id:
                # Create card info
                card_info = CardInfo(
                    reader_name=reader,
                    atr=list(atr),
                    atr_hex=smartcard.util.toHexString(atr, smartcard.util.HEX),
                    event_state=new_state,
                    event_type=event_type,
                    timestamp=time.time()
                )
                
                # Call user callback
                try:
                    self.mifare_tag_reader_callback(card_info)
                except Exception as e:
                    print(f"Error in user callback: {e}")
            
            # Debug output
            # self._print_state_info(reader, new_state, atr, event_type)
            
        except Exception as e:
            print(f"Error handling state change: {e}")
    
    def _print_state_info(self, reader: str, state: int, atr: List[int], event_type: Optional[CardEvent]):
        """Print detailed state information for debugging"""
        print(f"\n--- Reader: {reader} ---")
        if event_type:
            print(f"Event: {event_type.value.upper()}")
        
        if atr:
            print(f"ATR: {smartcard.util.toHexString(atr, smartcard.util.HEX)}")
        
        # Decode state flags
        flags = []
        if state & SCARD_STATE_UNAWARE:
            flags.append("UNAWARE")
        if state & SCARD_STATE_IGNORE:
            flags.append("IGNORE")
        if state & SCARD_STATE_UNAVAILABLE:
            flags.append("UNAVAILABLE")
        if state & SCARD_STATE_EMPTY:
            flags.append("EMPTY")
        if state & SCARD_STATE_PRESENT:
            flags.append("PRESENT")
        if state & SCARD_STATE_EXCLUSIVE:
            flags.append("EXCLUSIVE")
        if state & SCARD_STATE_INUSE:
            flags.append("INUSE")
        if state & SCARD_STATE_MUTE:
            flags.append("MUTE")
        if state & SCARD_STATE_CHANGED:
            flags.append("CHANGED")
        if state & SCARD_STATE_UNKNOWN:
            flags.append("UNKNOWN")
        
        print(f"State flags: {', '.join(flags) if flags else 'None'}")

    def mifare_tag_reader_callback(self, card_info: CardInfo):
        """
        Callback that reads MIFARE Classic cards and extracts tag ID from NDEF records
        
        This function performs:
        1. MIFARE Classic authentication using Key A
        2. Reading specific blocks containing NDEF data
        3. Parsing NDEF TLV structure
        4. Extracting and validating numeric tag ID from NDEF text records
        """
        # Only process card insertion events
        if card_info.event_type != CardEvent.INSERTED:
            return
        
        try:
            # Import required modules
            
            # MIFARE Classic configuration
            KEY_A   = [0xD3, 0xF7, 0xD3, 0xF7, 0xD3, 0xF7]
            BLOCKS = [0x04, 0x05, 0x06]  # Blocks to read (adjust as needed)
            
            # Find the reader that detected the card
            available_readers = readers()
            target_reader = None
            
            for reader in available_readers:
                if reader.name == card_info.reader_name:
                    target_reader = reader
                    break
            
            if not target_reader:
                print(f"❌ Could not find reader: {card_info.reader_name}")
                return
            
            # Create connection to the card
            try:
                conn = target_reader.createConnection()
                conn.connect()
            except Exception as e:
                print(f"❌ Failed to connect to card: {e}")
                return
            
            try:
                # Authenticate with Key A
                response, sw1, sw2 = conn.transmit([0xFF, 0x82, 0x00, 0x00, 0x06] + KEY_A)
                if (sw1, sw2) != (0x90, 0x00):
                    print(f"❌ Key loading failed: SW1={sw1:02X}, SW2={sw2:02X}")
                    return
                
                # Authenticate block 0 (or first block to read)
                auth_block = BLOCKS[0] if BLOCKS else 0x04
                response, sw1, sw2 = conn.transmit([0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, auth_block, 0x60, 0x00])
                if (sw1, sw2) != (0x90, 0x00):
                    print(f"❌ Block authentication failed: SW1={sw1:02X}, SW2={sw2:02X}")
                    return
                
                
                # Read data from specified blocks
                raw = []
                
                for block in BLOCKS:
                    try:
                        data, sw1, sw2 = conn.transmit([0xFF, 0xB0, 0x00, block, 0x10])
                        if (sw1, sw2) != (0x90, 0x00):
                            print(f"❌ Failed to read block {block:02X}: SW1={sw1:02X}, SW2={sw2:02X}")
                            return
                        raw.extend(data)
                    except Exception as e:
                        print(f"❌ Error reading block {block:02X}: {e}")
                        return
                
            finally:
                # Always disconnect
                try:
                    conn.disconnect()
                except:
                    pass
            
            # Extract NDEF TLV from raw data
            ndef_bytes = None
            
            for i in range(len(raw) - 1):
                if raw[i] == 0x03:  # NDEF TLV tag
                    length = raw[i + 1]
                    start = i + 2
                    
                    if start + length <= len(raw):
                        ndef_bytes = bytes(raw[start:start + length])
                        break
                    else:
                        print(f"⚠️  NDEF length extends beyond data: length={length}, available={len(raw)-start}")
            
            if not ndef_bytes:
                print("❌ No valid NDEF TLV found in card data")
                return
            
            # Parse NDEF message and extract tag ID
            tag_id = None
            
            try:
                for record in ndef.message_decoder(ndef_bytes):
                    if isinstance(record, ndef.TextRecord):
                        text = record.text.strip()
                        
                        if text.isdigit():
                            tag_id = int(text)
                            break
                        else:
                            print(f"⚠️  Text is not numeric: '{text}'")
            
            except Exception as e:
                print(f"❌ NDEF parsing failed: {e}")
                return
            
            # Handle result
            if tag_id is not None:
                # You can add your custom logic here
                # For example, send to a database, trigger an action, etc.
                self.handle_valid_tag_id(tag_id, card_info)
                
            else:
                self.handle_invalid_tag(card_info)
        
        except ImportError as e:
            print(f"❌ Missing required module: {e}")
            print("   Please install: pip install ndeflib")
        except Exception as e:
            print(f"❌ Unexpected error in MIFARE callback: {e}")
    

def main():
    """Example main function demonstrating usage"""
    print("NFC Card Listener Demo")
    print("======================")

    def handle_valid_tag_id(tag_id: int, card_info: CardInfo):
        """
        Handle a successfully read tag ID
        
        Args:
            tag_id: The numeric tag ID extracted from NDEF
            card_info: Card information from the listener
        """
        print(f"\nGot Tag ID: {tag_id}")
        # print(f"   Reader: {card_info.reader_name}")
        # print(f"   Time: {time.ctime(card_info.timestamp)}")


    def handle_invalid_tag_id(card_info: CardInfo):
        """
        Handle cases where tag reading failed or tag ID is invalid
        
        Args:
            card_info: Card information from the listener
        """
        print(f"\n❌ Invalid or unreadable tag")
        print(f"   Reader: {card_info.reader_name}")
        print(f"   Time: {time.ctime(card_info.timestamp)}")
    
    # Create listener with callback
    listener = NFCListener(handle_valid_tag_id=handle_valid_tag_id, handle_invalid_tag_id=handle_invalid_tag_id, poll_interval=0.5)
    
    # Start monitoring
    if not listener.start():
        print("Failed to start listener")
        return 1
    
    try:
        print("\nMonitoring for card events... (Press Ctrl+C to stop)")
        print("Please insert/remove NFC cards to see events")
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    finally:
        listener.stop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())