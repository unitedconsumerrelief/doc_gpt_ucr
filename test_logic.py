#!/usr/bin/env python3
"""
Test script to verify the new chunk validation and fallback logic
"""

def is_valid_primary_chunk(chunk, source):
    """
    Check if a chunk is valid for primary document-based answers.
    Must have at least 20 words and come from Clarity or Elevate documents.
    """
    # Check word count
    word_count = len(chunk.split())
    if word_count < 20:
        return False
    
    # Check if source is from primary programs (Clarity or Elevate)
    source_lower = source.lower()
    is_clarity = "clarity" in source_lower or "affiliate_training_packet" in source_lower
    is_elevate = "elevate" in source_lower
    
    return is_clarity or is_elevate

def get_program_sources_from_chunks(chunk_sources):
    """
    Extract program names from chunk sources, only counting Clarity and Elevate.
    """
    programs = set()
    for source in chunk_sources:
        source_lower = source.lower()
        if "clarity" in source_lower or "affiliate_training_packet" in source_lower:
            programs.add("Clarity")
        if "elevate" in source_lower:
            programs.add("Elevate")
    return sorted(list(programs))

# Test cases
def test_chunk_validation():
    print("🧪 Testing chunk validation logic...")
    
    # Test valid Clarity chunk
    valid_clarity_chunk = "This is a valid Clarity program document chunk with more than twenty words to ensure it meets the minimum word count requirement for processing."
    valid_clarity_source = "clarity_program_guide.pdf"
    
    # Test valid Elevate chunk
    valid_elevate_chunk = "The Elevate debt relief program offers comprehensive solutions for individuals struggling with various types of debt including credit cards, personal loans, and medical bills."
    valid_elevate_source = "elevate_handbook.pdf"
    
    # Test invalid chunk (too short)
    invalid_short_chunk = "Too short."
    invalid_short_source = "clarity.pdf"
    
    # Test invalid source (supporting document)
    invalid_source_chunk = "This is a valid chunk with enough words but it comes from a supporting document that should not be used for primary program answers."
    invalid_source = "Debt Comparison Table.pdf"
    
    # Test affiliate training packet
    affiliate_chunk = "The affiliate training packet contains detailed information about the Clarity program structure and how to properly assist clients with their debt relief needs."
    affiliate_source = "affiliate_training_packet_2025.pdf"
    
    # Run tests
    tests = [
        ("Valid Clarity", valid_clarity_chunk, valid_clarity_source, True),
        ("Valid Elevate", valid_elevate_chunk, valid_elevate_source, True),
        ("Too short", invalid_short_chunk, invalid_short_source, False),
        ("Invalid source", invalid_source_chunk, invalid_source, False),
        ("Affiliate training", affiliate_chunk, affiliate_source, True),
    ]
    
    for test_name, chunk, source, expected in tests:
        result = is_valid_primary_chunk(chunk, source)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status} {test_name}: {result} (expected {expected})")

def test_program_source_extraction():
    print("\n🧪 Testing program source extraction...")
    
    test_sources = [
        ["clarity.pdf", "elevate.pdf"],
        ["Debt Comparison Table.pdf", "clarity.pdf"],
        ["State List.pdf", "elevate.pdf", "affiliate_training_packet.pdf"],
        ["Unacceptable Credit Union.pdf"],
        ["clarity.pdf"],
        ["elevate.pdf"],
    ]
    
    for sources in test_sources:
        programs = get_program_sources_from_chunks(sources)
        print(f"Sources: {sources}")
        print(f"Programs: {programs}")
        print()

def test_footer_logic():
    print("🧪 Testing footer logic...")
    
    # Test cases for footer generation
    test_cases = [
        (set(), True, "📌 Source: ChatGPT"),  # Fallback used
        ({"clarity.pdf"}, False, "📌 Based on: Clarity"),  # Only Clarity
        ({"elevate.pdf"}, False, "📌 Based on: Elevate"),  # Only Elevate
        ({"clarity.pdf", "elevate.pdf"}, False, "📌 Based on: Clarity, Elevate"),  # Both
        ({"affiliate_training_packet.pdf"}, False, "📌 Based on: Clarity"),  # Affiliate packet
        ({"Debt Comparison Table.pdf"}, False, "📌 Source: ChatGPT"),  # Supporting doc only
    ]
    
    for sources, used_fallback, expected_footer in test_cases:
        if used_fallback:
            footer = "📌 Source: ChatGPT"
        elif sources:
            programs = get_program_sources_from_chunks(sources)
            if len(programs) == 0:
                # No valid primary programs found
                footer = "📌 Source: ChatGPT"
            elif len(programs) == 1:
                footer = f"📌 Based on: {programs[0]}"
            else:
                footer = f"📌 Based on: {', '.join(programs)}"
        else:
            footer = "📌 Source: ChatGPT"
        
        status = "✅ PASS" if footer == expected_footer else "❌ FAIL"
        print(f"{status} Sources: {sources}, Fallback: {used_fallback}")
        print(f"   Expected: {expected_footer}")
        print(f"   Got:      {footer}")
        print()

if __name__ == "__main__":
    test_chunk_validation()
    test_program_source_extraction()
    test_footer_logic()
    print("🎉 All tests completed!") 