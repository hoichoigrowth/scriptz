import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import time
from datetime import datetime
import re
import io
import hashlib
from typing import Dict, List, Any, Tuple

# Import optional dependencies with error handling
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import Color, red, orange, yellow, lightgrey, black
    from reportlab.lib.units import inch
    from reportlab.platypus.flowables import KeepTogether
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    import os
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import PyPDF2
    import pdfplumber
    PDF_EXTRACT_AVAILABLE = True
except ImportError:
    PDF_EXTRACT_AVAILABLE = False

# Configuration - Optimized for aggressive violation detection
MAX_CHARS_PER_CHUNK = 3000  # Smaller chunks for better analysis
OVERLAP_CHARS = 100  # Reduced overlap
MAX_TOKENS_OUTPUT = 1500  # Increased output tokens for more violations
CHUNK_DELAY = 0.5  # Reduced delay for faster analysis
MAX_RETRIES = 3

# Unicode text processing functions
def safe_unicode_text(text):
    """Safely handle Unicode text for PDF generation"""
    if not text:
        return ""
    
    try:
        # Ensure the text is properly encoded as UTF-8
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')
        elif not isinstance(text, str):
            text = str(text)
        
        # Handle special characters that might cause issues
        # Replace problematic characters with safe alternatives
        text = text.replace('\u200b', '')  # Remove zero-width space
        text = text.replace('\u200c', '')  # Remove zero-width non-joiner
        text = text.replace('\u200d', '')  # Remove zero-width joiner
        
        # For Bengali and other complex scripts, we need to be more careful
        # Keep the original text but ensure it's properly formatted
        return text
    except Exception as e:
        # Return a safe fallback
        return str(text).encode('ascii', errors='replace').decode('ascii')

def detect_language_fallback(text_sample):
    """Fallback language detection using character analysis"""
    if not text_sample:
        return "English"
    
    # Count characters from different scripts
    bengali_chars = sum(1 for char in text_sample if '\u0980' <= char <= '\u09FF')
    hindi_chars = sum(1 for char in text_sample if '\u0900' <= char <= '\u097F')
    tamil_chars = sum(1 for char in text_sample if '\u0B80' <= char <= '\u0BFF')
    telugu_chars = sum(1 for char in text_sample if '\u0C00' <= char <= '\u0C7F')
    gujarati_chars = sum(1 for char in text_sample if '\u0A80' <= char <= '\u0AFF')
    
    total_chars = len(text_sample)
    
    # If more than 10% of characters are from a specific script, detect that language
    if bengali_chars > total_chars * 0.1:
        return "Bengali"
    elif hindi_chars > total_chars * 0.1:
        return "Hindi"
    elif tamil_chars > total_chars * 0.1:
        return "Tamil"
    elif telugu_chars > total_chars * 0.1:
        return "Telugu"
    elif gujarati_chars > total_chars * 0.1:
        return "Gujarati"
    else:
        return "English"

def get_script_range(char):
    """Get the script range for a Unicode character"""
    code = ord(char)
    if 0x0900 <= code <= 0x097F:
        return "Devanagari (Hindi)"
    elif 0x0980 <= code <= 0x09FF:
        return "Bengali"
    elif 0x0A00 <= code <= 0x0A7F:
        return "Gurmukhi (Punjabi)"
    elif 0x0A80 <= code <= 0x0AFF:
        return "Gujarati"
    elif 0x0B00 <= code <= 0x0B7F:
        return "Oriya"
    elif 0x0B80 <= code <= 0x0BFF:
        return "Tamil"
    elif 0x0C00 <= code <= 0x0C7F:
        return "Telugu"
    elif 0x0C80 <= code <= 0x0CFF:
        return "Kannada"
    elif 0x0D00 <= code <= 0x0D7F:
        return "Malayalam"
    else:
        return "Other Unicode"

# S&P Violation Rules - Hybrid Context + Keywords Approach
VIOLATION_RULES = {
    "National_Anthem_Misuse": {
        "description": "Misuse of National Anthem for commercial use",
        "context": "Any commercial or promotional use of the Indian National Anthem, including background music, jingles, or promotional content",
        "keywords": ["national anthem", "jana gana mana", "commercial", "advertisement", "promotional", "jingle", "background music"],
        "severity": "critical"
    },
    "Personal_Information_Exposure": {
        "description": "Use of real personal information without consent (address, phone, email, license plate, photo)",
        "context": "Display of actual personal details, real addresses, working phone numbers, genuine email addresses, actual license plates, or real photographs of individuals",
        "keywords": ["phone number", "mobile number", "address", "email", "license plate", "personal photo", "real name", "contact details", "personal information"],
        "severity": "high"
    },
    "OTT_Platform_Promotion": {
        "description": "Promotion of any OTT or TV channel other than hoichoi",
        "context": "Any mention, promotion, or positive reference to competing streaming platforms, TV channels, or digital content providers",
        "keywords": ["netflix", "amazon prime", "hotstar", "zee5", "sony liv", "tv channel", "streaming platform", "digital platform", "ott platform", "prime video", "disney+"],
        "severity": "high"
    },
    "National_Emblem_Misuse": {
        "description": "Misuse of national emblems/assets as props; improper use of the Indian Flag",
        "context": "Using national flag, emblem, or symbols as costumes, props, decoration, or in any manner that violates the Flag Code of India",
        "keywords": ["indian flag", "tricolor", "tiranga", "ashoka chakra", "national emblem", "flag code", "national symbol", "emblem", "coat of arms"],
        "severity": "critical"
    },
    "National_Symbol_Distortion": {
        "description": "Distortion of national symbols/emblems or Indian map",
        "context": "Incorrect representation, alteration, or distortion of national symbols, emblems, or the geographical boundaries of India",
        "keywords": ["indian map", "national symbol", "emblem distortion", "flag distortion", "map distortion", "symbol alteration", "geographical boundaries"],
        "severity": "critical"
    },
    "Hurtful_References": {
        "description": "Hurtful references to real people/groups (football clubs, authors, etc.)",
        "context": "Negative, derogatory, or offensive references to real individuals, organizations, sports teams, or identifiable groups",
        "keywords": ["real person", "football club", "author", "celebrity", "public figure", "organization", "sports team", "derogatory", "offensive"],
        "severity": "medium"
    },
    "Self_Harm_Graphic_Content": {
        "description": "Graphic/self-harm or suicide attempts (must be suggestive, not detailed)",
        "context": "Detailed depiction of self-harm methods, explicit suicide attempts, or graphic content that could be instructional rather than suggestive",
        "keywords": ["suicide", "self-harm", "cutting", "hanging", "graphic violence", "self-injury", "suicide attempt", "harm oneself", "end life"],
        "severity": "critical"
    },
    "Acid_Attack_Depiction": {
        "description": "Depiction of acid attacks",
        "context": "Any portrayal of acid attacks, including preparation, execution, or aftermath, regardless of context",
        "keywords": ["acid attack", "acid throwing", "chemical burn", "disfigurement", "acid", "corrosive", "chemical attack"],
        "severity": "critical"
    },
    "Bomb_Weapon_Instructions": {
        "description": "Detailed instructions for making bombs, using weapons, or harmful tools",
        "context": "Step-by-step instructions, detailed explanations, or educational content about creating explosives, weapons, or harmful devices",
        "keywords": ["bomb making", "weapon instructions", "explosive", "harmful tools", "explosive device", "bomb recipe", "weapon tutorial"],
        "severity": "critical"
    },
    "Harmful_Product_Instructions": {
        "description": "Instructions or product mentions encouraging harm (e.g., using phenyl to commit suicide)",
        "context": "Content that suggests or instructs on using household products, chemicals, or substances for self-harm or harm to others",
        "keywords": ["phenyl", "poison", "harmful chemicals", "toxic substances", "household poison", "chemical harm", "toxic product"],
        "severity": "critical"
    },
    "Religious_Footwear_Context": {
        "description": "Wearing footwear in religious contexts or near idols",
        "context": "Characters wearing shoes or footwear inside temples, near religious idols, or in sacred spaces where it's culturally inappropriate",
        "keywords": ["shoes", "footwear", "temple", "idol", "religious place", "shrine", "sacred space", "sandals", "boots"],
        "severity": "high"
    },
    "Buddha_Idol_Misuse": {
        "description": "Inappropriate use/display of Buddha idols/pictures on props/clothing",
        "context": "Using Buddha's image or Buddhist symbols on clothing, accessories, or in inappropriate contexts that show disrespect",
        "keywords": ["buddha", "buddhist", "idol", "religious image", "clothing", "t-shirt", "accessory", "buddha statue", "buddhist symbol"],
        "severity": "high"
    },
    "Religious_Mockery": {
        "description": "Mockery of religious facts or symbols",
        "context": "Content that ridicules, mocks, or shows disrespect toward religious beliefs, practices, symbols, or sacred texts",
        "keywords": ["religious mockery", "sacred", "holy", "religious symbol", "faith", "mock", "ridicule", "disrespect", "blasphemy"],
        "severity": "critical"
    },
    "Caste_Religion_References": {
        "description": "Use of proverbs/colloquialisms that reference caste, religion, or community",
        "context": "Language that reinforces caste hierarchies, religious stereotypes, or discriminatory attitudes toward specific communities",
        "keywords": ["caste", "brahmin", "dalit", "community", "religious slur", "caste system", "untouchable", "higher caste", "lower caste"],
        "severity": "high"
    },
    "Social_Evils_Promotion": {
        "description": "Promotion of social evils (child marriage, dowry, son preference, etc.)",
        "context": "Content that normalizes, promotes, or presents harmful social practices in a positive light without showing consequences",
        "keywords": ["child marriage", "dowry", "son preference", "female infanticide", "social evil", "harmful practice", "discrimination"],
        "severity": "critical"
    },
    "Unauthorized_Branding": {
        "description": "Unauthorized branding/endorsement; brand names must be blurred",
        "context": "Visible brand logos, product names, or commercial endorsements without proper clearance or blurring",
        "keywords": ["brand name", "logo", "trademark", "product placement", "endorsement", "commercial brand", "brand logo", "product name"],
        "severity": "medium"
    },
    "Credit_List_Changes": {
        "description": "Unapproved or post-deadline changes in the credit list",
        "context": "Modifications to cast, crew, or production credits after final approval or without proper authorization",
        "keywords": ["credits", "cast", "crew", "production team", "acknowledgment", "credit list", "cast list", "crew list"],
        "severity": "medium"
    },
    "Alcohol_Cigarette_Brands": {
        "description": "Display of alcohol/cigarette brands/logos without marketing team approval",
        "context": "Visible alcohol or tobacco brand names, logos, or products without proper marketing clearance",
        "keywords": ["alcohol brand", "cigarette brand", "tobacco", "liquor", "beer", "wine", "whiskey", "cigarette logo", "tobacco brand"],
        "severity": "high"
    },
    "Smoking_Disclaimer_Missing": {
        "description": "Absence of 'Smoking Kills' message during smoking scenes",
        "context": "Smoking scenes without appropriate health warnings or disclaimers as required by regulations",
        "keywords": ["smoking", "cigarette", "tobacco", "disclaimer", "warning", "smoking kills", "health warning", "tobacco warning"],
        "severity": "medium"
    },
    "Content_Disclaimer_Missing": {
        "description": "Missing special disclaimers for violent, gory, or sexually explicit content",
        "context": "Content requiring viewer discretion or age-appropriate warnings without proper disclaimers",
        "keywords": ["violence", "gore", "sexual content", "explicit", "disclaimer", "viewer discretion", "age appropriate", "content warning"],
        "severity": "medium"
    },
    "Unapproved_Endorsements": {
        "description": "Unapproved endorsements or acknowledgments in end credits",
        "context": "Thank you messages, acknowledgments, or endorsements in credits that haven't been approved by the content team",
        "keywords": ["endorsement", "acknowledgment", "credits", "sponsor", "thanks", "end credits", "acknowledgement", "special thanks"],
        "severity": "medium"
    },
    "Animal_Harm_Depiction": {
        "description": "Depiction of harm or killing of animals during filming",
        "context": "Content showing actual harm to animals during production, cruelty to animals, or realistic depictions of animal suffering",
        "keywords": ["animal harm", "animal killing", "cruelty", "abuse", "violence", "animal cruelty", "animal suffering", "harm animals"],
        "severity": "critical"
    },
    "Child_Adult_Behavior": {
        "description": "Child actors shown behaving like adults or speaking mature dialogue",
        "context": "Child characters using adult language, exhibiting mature behavior, or being placed in age-inappropriate situations",
        "keywords": ["child actor", "mature dialogue", "adult behavior", "inappropriate", "child character", "adult language", "age inappropriate"],
        "severity": "high"
    },
    "Child_Abuse_Content": {
        "description": "Any form of child abuse—physical, sexual, or psychological",
        "context": "Content depicting, suggesting, or normalizing any form of abuse toward children, including physical, emotional, or sexual abuse",
        "keywords": ["child abuse", "physical abuse", "sexual abuse", "psychological abuse", "child harm", "abuse child", "child violence"],
        "severity": "critical"
    }
}

# Streamlit App Configuration
st.set_page_config(
    page_title="hoichoi S&P Compliance Analyzer",
    page_icon="🎬",
    layout="wide"
)

# Authentication Functions
def check_email_domain(email: str) -> bool:
    """Check if email belongs to hoichoi.tv domain"""
    return email.lower().strip().endswith('@hoichoi.tv')

def authenticate_user():
    """Handle user authentication for hoichoi.tv employees only"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        # Custom CSS for login page
        st.markdown("""
        <style>
        .login-header {
            background: linear-gradient(90deg, #ff6b6b, #4ecdc4);
            padding: 2rem;
            border-radius: 15px;
            color: white;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .login-container {
            background: white;
            padding: 2rem;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            border: 1px solid #e0e0e0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="login-header">
            <h1>🎬 hoichoi S&P Compliance System</h1>
            <h3>Standards & Practices Content Review Platform</h3>
            <p>Secure access for hoichoi content team members</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.markdown('<div class="login-container">', unsafe_allow_html=True)
                
                st.subheader("🔐 Employee Access Portal")
                st.write("Please login with your hoichoi corporate email address")
                
                email = st.text_input(
                    "Corporate Email Address",
                    placeholder="yourname@hoichoi.tv",
                    help="Only @hoichoi.tv email addresses are authorized"
                )
                
                password = st.text_input(
                    "Password",
                    type="password",
                    help="Enter your corporate password"
                )
                
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("🚀 Login", type="primary", use_container_width=True):
                        if email and password:
                            if check_email_domain(email):
                                # Simple password check (in production, use proper authentication)
                                if len(password) >= 6:  # Basic password validation
                                    st.session_state.authenticated = True
                                    st.session_state.user_email = email
                                    st.session_state.user_name = email.split('@')[0].replace('.', ' ').title()
                                    st.session_state.is_admin = email.lower() in ['admin@hoichoi.tv', 'sp@hoichoi.tv', 'content@hoichoi.tv']
                                    st.success("✅ Login successful! Redirecting...")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("❌ Password must be at least 6 characters long")
                            else:
                                st.error("❌ Access denied. Only @hoichoi.tv email addresses are authorized.")
                                st.warning("This system is restricted to hoichoi content team members only.")
                        else:
                            st.error("❌ Please enter both email and password")
                
                with col_b:
                    if st.button("ℹ️ Help", use_container_width=True):
                        st.info("""
                        **Need Access?**
                        - Contact IT department for account setup
                        - Must use corporate @hoichoi.tv email
                        - For support: it@hoichoi.tv
                        """)
                
                st.divider()
                st.markdown("""
                <div style='text-align: center; color: #666; font-size: 0.9em;'>
                    <p>🔒 This is a secure system for hoichoi content review</p>
                    <p>📧 Access restricted to @hoichoi.tv employees only</p>
                    <p>🛡️ All activities are logged for security purposes</p>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
        
        return False
    
    return True

def get_api_key():
    """Get OpenAI API key from Streamlit secrets or user input"""
    try:
        return st.secrets.get("OPENAI_API_KEY", None)
    except:
        return None

def setup_unicode_fonts():
    """Setup Unicode fonts for multilingual PDF support"""
    try:
        # Register Unicode fonts for better language support
        # In production, you should include actual font files
        # For now, using default fonts with Unicode support
        return True
    except:
        return False

def detect_language(text_sample):
    """Detect the primary language of the text using improved AI detection"""
    api_key = get_api_key()
    if not OPENAI_AVAILABLE or not api_key:
        # Fallback language detection without AI
        return detect_language_fallback(text_sample)
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Take a larger sample for better detection
        sample = text_sample[:2000] if len(text_sample) > 2000 else text_sample
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a language detection expert. Identify the primary language of the given text. Return ONLY the language name in English. Common languages include: English, Bengali, Hindi, Tamil, Telugu, Gujarati, Marathi, Punjabi, Urdu, Malayalam, Kannada, Odia, Assamese."},
                {"role": "user", "content": f"What language is this text primarily written in? Respond with just the language name.\n\nText: {sample}"}
            ],
            max_tokens=10,
            temperature=0
        )
        
        detected_language = response.choices[0].message.content.strip()
        
        # Validate the detected language
        valid_languages = ['English', 'Bengali', 'Hindi', 'Tamil', 'Telugu', 'Gujarati', 'Marathi', 'Punjabi', 'Urdu', 'Malayalam', 'Kannada', 'Odia', 'Assamese']
        if detected_language in valid_languages:
            return detected_language
        else:
            return detect_language_fallback(text_sample)
        
    except Exception as e:
        return detect_language_fallback(text_sample)

def extract_text_from_pdf_bytes(file_bytes):
    """Extract text from uploaded PDF file bytes with page preservation"""
    if not PDF_EXTRACT_AVAILABLE:
        st.error("❌ PDF extraction libraries not available. Please install PyPDF2 and pdfplumber.")
        return None, []
    
    try:
        pages_data = []
        full_text = ""
        
        # Try using pdfplumber first (better for complex layouts)
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text() or ""
                    
                    if page_text.strip():
                        pages_data.append({
                            'page_number': page_num,
                            'text': page_text.strip(),
                            'original_page': page_num  # Preserve original page number
                        })
                        full_text += f"\n=== ORIGINAL PAGE {page_num} ===\n{page_text}\n"
        except:
            # Fallback to PyPDF2
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_text = page.extract_text() or ""
                
                if page_text.strip():
                    pages_data.append({
                        'page_number': page_num,
                        'text': page_text.strip(),
                        'original_page': page_num  # Preserve original page number
                    })
                    full_text += f"\n=== ORIGINAL PAGE {page_num} ===\n{page_text}\n"
        
        return full_text, pages_data
        
    except Exception as e:
        st.error(f"Error extracting text from PDF: {e}")
        return None, []

def extract_text_from_docx_bytes(file_bytes):
    """Extract text from uploaded DOCX file bytes with enhanced screenplay parsing"""
    if not DOCX_AVAILABLE:
        st.error("❌ python-docx not available. Please check requirements.txt")
        return None, []
    
    try:
        doc = Document(io.BytesIO(file_bytes))
        pages_data = []
        full_text = ""
        
        # Enhanced screenplay parsing
        current_page = 1
        current_page_text = ""
        char_count = 0
        
        screenplay_elements = []
        
        for para in doc.paragraphs:
            para_text = para.text.strip()
            
            if not para_text:
                continue
            
            # Detect screenplay elements
            element_type = detect_screenplay_element(para_text, para)
            
            screenplay_elements.append({
                'text': para_text,
                'type': element_type,
                'page': current_page
            })
            
            # Check for manual page breaks
            if has_page_break(para):
                # Save current page
                if current_page_text.strip():
                    pages_data.append({
                        'page_number': current_page,
                        'text': current_page_text.strip(),
                        'original_page': current_page,
                        'screenplay_elements': [e for e in screenplay_elements if e['page'] == current_page]
                    })
                    full_text += f"\n=== ORIGINAL PAGE {current_page} ===\n{current_page_text}\n"
                
                current_page += 1
                current_page_text = ""
                char_count = 0
            else:
                current_page_text += para_text + "\n"
                char_count += len(para_text) + 1
                
                # Automatic page break based on character count (approximate)
                if char_count > 2000:  # Rough estimate for one page
                    pages_data.append({
                        'page_number': current_page,
                        'text': current_page_text.strip(),
                        'original_page': current_page,
                        'screenplay_elements': [e for e in screenplay_elements if e['page'] == current_page]
                    })
                    full_text += f"\n=== ORIGINAL PAGE {current_page} ===\n{current_page_text}\n"
                    
                    current_page += 1
                    current_page_text = ""
                    char_count = 0
        
        # Add remaining text
        if current_page_text.strip():
            pages_data.append({
                'page_number': current_page,
                'text': current_page_text.strip(),
                'original_page': current_page,
                'screenplay_elements': [e for e in screenplay_elements if e['page'] == current_page]
            })
            full_text += f"\n=== ORIGINAL PAGE {current_page} ===\n{current_page_text}\n"
        
        return full_text, pages_data
        
    except Exception as e:
        st.error(f"Error extracting text: {e}")
        return None, []

def detect_screenplay_element(text, para):
    """Detect screenplay element type (scene heading, character, dialogue, action, etc.)"""
    text_upper = text.upper()
    
    # Scene headings
    if (text_upper.startswith(('INT.', 'EXT.', 'INTERIOR', 'EXTERIOR')) or
        re.match(r'^(INT|EXT)\.?\s+', text_upper)):
        return 'SCENE_HEADING'
    
    # Character names (usually centered or in caps)
    if (text.isupper() and len(text.split()) <= 3 and 
        not text.startswith(('INT.', 'EXT.')) and
        len(text) < 50):
        return 'CHARACTER'
    
    # Parentheticals
    if text.startswith('(') and text.endswith(')'):
        return 'PARENTHETICAL'
    
    # Transitions
    if (text_upper.endswith(('TO:', 'OUT:', 'IN:')) or
        text_upper in ['FADE IN:', 'FADE OUT:', 'CUT TO:', 'DISSOLVE TO:']):
        return 'TRANSITION'
    
    # Action/Description (default for longer text)
    if len(text) > 100:
        return 'ACTION'
    
    # Dialogue (shorter text that's not other elements)
    return 'DIALOGUE'

def has_page_break(para):
    """Check if paragraph has a page break"""
    try:
        # Check for page break in Word document
        if hasattr(para, '_element'):
            for br in para._element.xpath('.//w:br[@w:type="page"]'):
                return True
        return False
    except:
        return False

def generate_ai_solution(violation_text, violation_type, explanation, detected_language, api_key):
    """Generate AI solution for the violation in the detected language based on hybrid analysis"""
    if not OPENAI_AVAILABLE or not api_key:
        return "AI solution generation not available"
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Map violation type to specific guidance
        guideline_context = {
            "National_Anthem_Misuse": "Remove commercial use of national anthem; use instrumental version or replace with original music",
            "Personal_Information_Exposure": "Blur/mask personal information; use fictional phone numbers and addresses",
            "OTT_Platform_Promotion": "Remove references to competing platforms; replace with generic terms or hoichoi references",
            "National_Emblem_Misuse": "Remove improper flag usage; ensure respectful display according to Flag Code of India",
            "National_Symbol_Distortion": "Restore accurate representation of national symbols and Indian map",
            "Religious_Footwear_Context": "Remove footwear in religious settings; ensure actors are barefoot near idols/temples",
            "Buddha_Idol_Misuse": "Remove Buddha images from clothing/inappropriate contexts; use respectfully or remove",
            "Religious_Mockery": "Rewrite dialogue to be respectful of religious beliefs and symbols",
            "Caste_Religion_References": "Replace with neutral language; avoid caste/community-specific terms",
            "Social_Evils_Promotion": "Reframe to show negative consequences; don't glorify harmful practices",
            "Self_Harm_Graphic_Content": "Make suggestive rather than explicit; focus on emotional impact, not graphic details",
            "Acid_Attack_Depiction": "Remove or significantly tone down; use off-screen treatment",
            "Child_Adult_Behavior": "Rewrite dialogue age-appropriately; ensure child actors behave naturally",
            "Child_Abuse_Content": "Remove completely; find alternative plot devices",
            "Unauthorized_Branding": "Blur visible brand names and logos; use generic alternatives",
            "Alcohol_Cigarette_Brands": "Blur alcohol/tobacco brands; use generic packaging",
            "Smoking_Disclaimer_Missing": "Add 'Smoking Kills' disclaimer during smoking scenes",
            "Animal_Harm_Depiction": "Remove animal harm scenes; use CGI or off-screen treatment"
        }
        
        specific_guidance = guideline_context.get(violation_type, "Revise content to comply with broadcasting standards")
        
        prompt = f"""You are an expert content editor for hoichoi digital platform. Generate a compliant revision for this S&P violation detected through hybrid analysis (keywords + context).

VIOLATION DETAILS:
- Type: {violation_type}
- Problematic Content: "{violation_text}"
- Issue: {explanation}
- Content Language: {detected_language}
- Specific Guidance: {specific_guidance}

INSTRUCTIONS:
1. Provide a revised version that eliminates the S&P violation completely
2. Maintain the original creative intent where possible
3. Keep the same language as the original content ({detected_language})
4. Ensure the solution is appropriate for Indian digital content standards
5. Make the minimum necessary changes to achieve compliance

Return ONLY the revised content solution, nothing else."""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert content editor specializing in S&P compliance for hoichoi digital platform. Provide practical, implementable solutions."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.3
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error generating solution: {str(e)}"

def chunk_text(text, max_chars=3000):  # Reduced chunk size for better analysis
    """Split text into analysis chunks while preserving screenplay structure"""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    
    # Split by lines first to preserve screenplay structure
    lines = text.split('\n')
    current_chunk = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if adding this line would exceed max_chars
        if len(current_chunk + line + '\n') > max_chars and current_chunk:
            # Save current chunk
            chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
    
    # Add remaining chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Ensure no chunk is too small (merge small chunks)
    final_chunks = []
    for chunk in chunks:
        if len(chunk) < 500 and final_chunks:  # If chunk is too small, merge with previous
            final_chunks[-1] += '\n\n' + chunk
        else:
            final_chunks.append(chunk)
    
    return final_chunks

def create_analysis_prompt():
    """Create aggressive violation detection prompt for comprehensive script analysis"""
    
    return """You are an S&P Compliance Reviewer for hoichoi. Your job is to ACTIVELY FIND and FLAG violations in this screenplay/script content. Be thorough and aggressive in detecting violations - err on the side of flagging rather than missing violations.

ANALYZE EVERYTHING: Dialogues, scene descriptions, action lines, character names, props, settings, visual elements, transitions, and any other screenplay content.

🎯 FIND VIOLATIONS IN THESE 24 AREAS:

1. **National Anthem Commercial Use** - Any use of Indian national anthem for commercial/promotional purposes
2. **Personal Information** - Real phone numbers, addresses, emails, license plates, actual photos
3. **Competitor Platform Promotion** - Any mention of Netflix, Amazon Prime, Hotstar, Disney+, Zee5, Sony Liv, or other streaming platforms
4. **National Flag/Emblem Misuse** - Improper use of Indian flag, national symbols, or emblems as props/costumes
5. **National Symbol Distortion** - Incorrect Indian map, distorted national symbols
6. **Hurtful Real References** - Negative references to real people, celebrities, organizations, sports teams
7. **Graphic Self-Harm/Suicide** - Detailed self-harm methods, explicit suicide scenes
8. **Acid Attack Scenes** - Any depiction of acid attacks
9. **Weapon/Bomb Instructions** - Detailed instructions for making weapons or explosives
10. **Harmful Product Instructions** - Using household products like phenyl for harm
11. **Religious Footwear** - Wearing shoes in temples, near idols, religious spaces
12. **Buddha Idol Misuse** - Buddha images on clothing, inappropriate contexts
13. **Religious Mockery** - Mocking religious beliefs, symbols, practices
14. **Caste/Religion Slurs** - Language reinforcing caste hierarchies, religious stereotypes
15. **Social Evils Promotion** - Glorifying child marriage, dowry, gender discrimination
16. **Visible Brand Names** - Unblurred product brands, logos, commercial endorsements
17. **Unauthorized Credits** - Unapproved changes to cast/crew credits
18. **Alcohol/Tobacco Brands** - Visible alcohol or cigarette brand names/logos
19. **Missing Smoking Warnings** - Smoking scenes without "Smoking Kills" disclaimer
20. **Missing Content Warnings** - Violent/sexual content without appropriate disclaimers
21. **Unapproved Endorsements** - Unauthorized thank-you messages in credits
22. **Animal Harm** - Actual or realistic animal cruelty, killing, suffering
23. **Child Inappropriate Behavior** - Children using adult language or mature behavior
24. **Child Abuse Content** - Any form of child abuse (physical, sexual, psychological)

🔍 DETECTION STRATEGY:
- READ EVERY LINE carefully
- LOOK FOR both obvious and subtle violations
- CHECK dialogue for inappropriate language/references
- EXAMINE scene descriptions for problematic content
- ANALYZE character actions and behaviors
- REVIEW props, settings, and visual elements
- FLAG anything that could potentially violate guidelines

⚠️ BE AGGRESSIVE IN DETECTION:
- When in doubt, FLAG IT
- Better to over-detect than miss violations
- Look for implied violations, not just explicit ones
- Consider cultural context and Indian sensitivities
- Check for subtle discriminatory language
- Look for brand names, logos, or commercial elements

EXAMPLES OF WHAT TO FLAG:

**Dialogue Examples:**
- "Let's watch that new show on Netflix tonight"
- "People from his community are always like that"
- "Mix phenyl with water and drink it"
- "She deserves dowry for marrying him"

**Scene Description Examples:**
- "Character enters temple wearing shoes"
- "Close-up of Coca-Cola logo on bottle"
- "Character hangs Indian flag as curtain"
- "Buddha statue used as decoration on t-shirt"

**Action Line Examples:**
- "Character smokes cigarette (no disclaimer shown)"
- "Animal is actually harmed during fight scene"
- "Child actor uses profanity"
- "Character performs detailed self-harm"

📋 ANALYSIS CHECKLIST:
□ Read every dialogue line
□ Examine every scene description
□ Check every character action
□ Look for brand names/logos
□ Verify religious/cultural sensitivity
□ Check for inappropriate child content
□ Look for discriminatory language
□ Examine props and settings
□ Check for competitor platform mentions
□ Look for missing disclaimers

Return violations in this JSON format:
{
  "violations": [
    {
      "violationText": "Exact text from script",
      "violationType": "One of the 24 violation types",
      "explanation": "Why this violates the guideline",
      "suggestedAction": "How to fix it",
      "severity": "critical|high|medium|low",
      "location": "dialogue|scene_description|action_line|character_name|prop|setting|other"
    }
  ]
}

REMEMBER: Your job is to FIND violations, not to excuse them. Be thorough, be aggressive, be comprehensive. Analyze every element of the screenplay."""

def analyze_chunk(chunk, chunk_num, total_chunks, api_key):
    """Analyze single chunk with aggressive violation detection"""
    if not OPENAI_AVAILABLE or not api_key:
        return {"violations": []}
    
    try:
        client = OpenAI(api_key=api_key)
        
        prompt = create_analysis_prompt()
        
        # More direct and aggressive prompt
        full_prompt = f"""{prompt}

CONTENT TO ANALYZE (Chunk {chunk_num}/{total_chunks}):
{chunk}

INSTRUCTIONS:
1. READ every line carefully
2. FIND violations in dialogues, scene descriptions, action lines, character names, props, settings
3. FLAG anything that could violate the 24 guidelines
4. Be AGGRESSIVE in detection - when in doubt, flag it
5. Return violations in JSON format

JSON RESPONSE:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an aggressive S&P compliance reviewer. Your job is to FIND violations. Be thorough and flag everything that could potentially violate guidelines. Better to over-detect than miss violations."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.1,
            max_tokens=1500,  # Increased token limit
            timeout=90  # Increased timeout
        )
        
        result = response.choices[0].message.content.strip()
        
        # More robust JSON parsing
        try:
            parsed_result = json.loads(result)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                try:
                    parsed_result = json.loads(json_match.group())
                except:
                    # If still fails, try to find just the violations array
                    violations_match = re.search(r'"violations":\s*\[(.*?)\]', result, re.DOTALL)
                    if violations_match:
                        try:
                            parsed_result = {"violations": json.loads(f'[{violations_match.group(1)}]')}
                        except:
                            return {"violations": []}
                    else:
                        return {"violations": []}
            else:
                return {"violations": []}
        
        # Ensure violations are properly formatted
        if 'violations' in parsed_result and isinstance(parsed_result['violations'], list):
            valid_violations = []
            for violation in parsed_result['violations']:
                if isinstance(violation, dict):
                    # Ensure required fields exist
                    if 'violationText' in violation and 'violationType' in violation:
                        # Set default values for missing fields
                        violation.setdefault('explanation', 'S&P violation detected')
                        violation.setdefault('suggestedAction', 'Review and modify content')
                        violation.setdefault('severity', 'medium')
                        violation.setdefault('location', 'content')
                        valid_violations.append(violation)
            
            return {"violations": valid_violations}
        
        return {"violations": []}
        
    except Exception as e:
        st.error(f"Error analyzing chunk {chunk_num}: {e}")
        return {"violations": []}

def find_page_number(violation_text, pages_data):
    """Find which page contains the violation using original page numbers"""
    for page_data in pages_data:
        if violation_text in page_data['text']:
            return page_data.get('original_page', page_data['page_number'])
    
    # Fuzzy matching
    search_text = violation_text[:50] if len(violation_text) > 50 else violation_text
    for page_data in pages_data:
        if search_text in page_data['text']:
            return page_data.get('original_page', page_data['page_number'])
    
    return 1

def analyze_document(text, pages_data, api_key):
    """Analyze entire document with aggressive violation detection and better Unicode handling"""
    if not text or not api_key:
        return {"violations": [], "summary": {}}
    
    # Show text analysis debug info
    st.markdown("### 🔍 **Text Analysis Debug Info**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Characters", len(text))
    with col2:
        st.metric("Total Lines", len(text.split('\n')))
    with col3:
        unicode_chars = sum(1 for char in text if ord(char) > 127)
        st.metric("Unicode Characters", unicode_chars)
    
    # Show character distribution
    if unicode_chars > 0:
        st.info(f"📝 **Unicode Content Detected**: {unicode_chars} non-ASCII characters found")
        
        # Show first 200 characters as preview
        with st.expander("📄 Text Preview (First 200 characters)"):
            preview_text = text[:200]
            st.text(preview_text)
            st.write(f"**Character breakdown**: ASCII: {len(preview_text) - sum(1 for c in preview_text if ord(c) > 127)}, Unicode: {sum(1 for c in preview_text if ord(c) > 127)}")
    
    # Detect language with better feedback
    detected_language = detect_language(text)
    st.info(f"🌐 **Content Language:** {detected_language} | 🔍 **Analysis Method:** Aggressive Detection | 📋 **Coverage:** Complete Script Analysis")
    
    # Show what we're analyzing
    st.markdown("### 📋 **Analysis Coverage:**")
    st.markdown("- ✅ **Dialogues**: All character conversations and speech")
    st.markdown("- ✅ **Scene Descriptions**: Location setups, visual descriptions")
    st.markdown("- ✅ **Action Lines**: Character actions, movements, behaviors")
    st.markdown("- ✅ **Character Names**: All character references")
    st.markdown("- ✅ **Props & Settings**: Objects, locations, visual elements")
    st.markdown("- ✅ **Transitions**: Scene changes, cuts, fades")
    
    chunks = chunk_text(text)
    all_violations = []
    successful_chunks = 0
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    st.info(f"🔍 **Analyzing {len(chunks)} chunks** for comprehensive violation detection...")
    
    for i, chunk in enumerate(chunks):
        progress = (i + 1) / len(chunks)
        progress_bar.progress(progress)
        status_text.text(f"🔍 Analyzing chunk {i+1}/{len(chunks)} - Looking for violations...")
        
        # Show chunk analysis info
        chunk_unicode = sum(1 for char in chunk if ord(char) > 127)
        chunk_info = f"Chunk {i+1}: {len(chunk)} chars, {chunk_unicode} Unicode chars"
        
        # Show chunk preview for debugging
        with st.expander(f"📄 {chunk_info}"):
            st.text(chunk[:300] + "..." if len(chunk) > 300 else chunk)
            if chunk_unicode > 0:
                st.success(f"✅ Unicode content detected: {chunk_unicode} characters")
        
        analysis = analyze_chunk(chunk, i+1, len(chunks), api_key)
        
        if 'violations' in analysis and analysis['violations']:
            st.success(f"⚠️ Found {len(analysis['violations'])} violations in chunk {i+1}")
            
            # Show violation details
            for j, violation in enumerate(analysis['violations']):
                violation_text = violation.get('violationText', '')
                violation_unicode = sum(1 for char in violation_text if ord(char) > 127)
                st.write(f"   → Violation {j+1}: {violation.get('violationType', 'Unknown')} ({len(violation_text)} chars, {violation_unicode} Unicode)")
                
                violation['pageNumber'] = find_page_number(violation_text, pages_data)
                violation['chunkNumber'] = i + 1
                violation['detectedLanguage'] = detected_language
                violation['unicodeChars'] = violation_unicode
                all_violations.append(violation)
            successful_chunks += 1
        else:
            st.info(f"✅ No violations found in chunk {i+1}")
    
    # Generate AI solutions for violations
    if all_violations:
        status_text.text("🤖 Generating AI solutions for violations...")
        solution_errors = 0
        
        for i, violation in enumerate(all_violations):
            progress = (i + 1) / len(all_violations)
            progress_bar.progress(progress)
            
            try:
                ai_solution = generate_ai_solution(
                    violation.get('violationText', ''),
                    violation.get('violationType', ''),
                    violation.get('explanation', ''),
                    detected_language,
                    api_key
                )
                violation['aiSolution'] = ai_solution
                
                # Check if AI solution has Unicode
                solution_unicode = sum(1 for char in ai_solution if ord(char) > 127)
                violation['aiSolutionUnicode'] = solution_unicode
                
            except Exception as e:
                solution_errors += 1
                violation['aiSolution'] = f"Error generating solution: {str(e)}"
                violation['aiSolutionUnicode'] = 0
        
        if solution_errors > 0:
            st.warning(f"⚠️ {solution_errors} AI solution generation errors occurred")
    
    progress_bar.progress(1.0)
    status_text.text(f"✅ Analysis complete! Found {len(all_violations)} violations across {len(chunks)} chunks")
    
    # Show Unicode analysis summary
    if all_violations:
        total_violation_unicode = sum(v.get('unicodeChars', 0) for v in all_violations)
        total_solution_unicode = sum(v.get('aiSolutionUnicode', 0) for v in all_violations)
        
        st.markdown("### 📊 **Unicode Analysis Summary**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Violations", len(all_violations))
        with col2:
            st.metric("Unicode in Violations", total_violation_unicode)
        with col3:
            st.metric("Unicode in Solutions", total_solution_unicode)
    
    # Remove duplicates but be less aggressive about it
    unique_violations = []
    seen_violations = set()
    
    for violation in all_violations:
        v_text = violation.get('violationText', '')
        v_type = violation.get('violationType', '')
        
        # Create a more lenient duplicate detection
        duplicate_key = (v_text[:50], v_type)  # Only check first 50 chars for similarity
        
        if duplicate_key not in seen_violations:
            seen_violations.add(duplicate_key)
            unique_violations.append(violation)
    
    # Sort by severity and page
    severity_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
    unique_violations.sort(key=lambda x: (
        -severity_order.get(x.get('severity', 'low'), 1),  # Sort by severity first
        x.get('pageNumber', 0)  # Then by page number
    ))
    
    return {
        "violations": unique_violations,
        "detectedLanguage": detected_language,
        "summary": {
            "totalViolations": len(unique_violations),
            "totalPages": len(pages_data),
            "chunksAnalyzed": len(chunks),
            "chunksWithViolations": successful_chunks,
            "successRate": f"{(successful_chunks/len(chunks)*100):.1f}%" if chunks else "0%",
            "unicodeChars": sum(1 for char in text if ord(char) > 127),
            "totalChars": len(text)
        }
    }

def generate_excel_report(violations, filename):
    """Generate Excel report with AI solutions - Enhanced Unicode support"""
    if not EXCEL_AVAILABLE:
        st.error("Excel generation not available. Please install openpyxl.")
        return None
    
    try:
        # Create enhanced dataframe with proper Unicode handling
        excel_data = []
        for i, violation in enumerate(violations, 1):
            # Safely handle Unicode text
            violation_text = safe_unicode_text(violation.get('violationText', 'N/A'))
            ai_solution = safe_unicode_text(violation.get('aiSolution', 'N/A'))
            explanation = safe_unicode_text(violation.get('explanation', 'N/A'))
            suggested_action = safe_unicode_text(violation.get('suggestedAction', 'N/A'))
            
            excel_data.append({
                'S.No': i,
                'Page Number': violation.get('pageNumber', 'N/A'),
                'Violation Type': violation.get('violationType', 'Unknown'),
                'Severity': violation.get('severity', 'medium').upper(),
                'Violated Text': violation_text,
                'Explanation': explanation,
                'Suggested Action': suggested_action,
                'AI Solution': ai_solution,
                'Language': violation.get('detectedLanguage', 'Unknown'),
                'Location': violation.get('location', 'content'),
                'Status': 'PENDING REVIEW'
            })
        
        df = pd.DataFrame(excel_data)
        buffer = io.BytesIO()
        
        # Use UTF-8 encoding for Excel
        with pd.ExcelWriter(buffer, engine='openpyxl', options={'strings_to_urls': False}) as writer:
            df.to_excel(writer, sheet_name='Violations', index=False)
            
            # Summary sheet
            summary_data = {
                'Metric': ['Total Violations', 'Critical', 'High', 'Medium', 'Low', 'Content Language'],
                'Count': [
                    len(violations),
                    len([v for v in violations if v.get('severity') == 'critical']),
                    len([v for v in violations if v.get('severity') == 'high']),
                    len([v for v in violations if v.get('severity') == 'medium']),
                    len([v for v in violations if v.get('severity') == 'low']),
                    violations[0].get('detectedLanguage', 'Unknown') if violations else 'Unknown'
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Format the sheets for better readability
            workbook = writer.book
            violation_sheet = workbook['Violations']
            
            # Auto-adjust column widths and handle Unicode
            for column in violation_sheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        cell_value = str(cell.value) if cell.value else ""
                        if len(cell_value) > max_length:
                            max_length = len(cell_value)
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
                violation_sheet.column_dimensions[column_letter].width = adjusted_width
        
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating Excel report: {e}")
        return None

def create_unicode_paragraph(text, style, detected_language='English'):
    """Create a paragraph with proper Unicode support"""
    try:
        # Handle Unicode text properly
        if isinstance(text, str):
            # Ensure text is properly encoded
            safe_text = text.encode('utf-8', errors='ignore').decode('utf-8')
        else:
            safe_text = str(text)
        
        return Paragraph(safe_text, style)
    except Exception as e:
        # Fallback to basic text if Unicode fails
        return Paragraph(str(text).encode('ascii', errors='ignore').decode('ascii'), style)

def generate_violations_report_pdf(violations, filename):
    """Generate PDF report with violation details and AI solutions - Enhanced Unicode support"""
    if not PDF_AVAILABLE:
        st.error("PDF generation not available. Please install reportlab.")
        return None
    
    try:
        setup_unicode_fonts()
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title with better Unicode support
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            spaceAfter=30,
            textColor=Color(0.2, 0.2, 0.6),
            alignment=1,
            fontName='Helvetica-Bold'
        )
        
        story.append(Paragraph("hoichoi S&P COMPLIANCE VIOLATION REPORT", title_style))
        story.append(Paragraph(f"Document: {safe_unicode_text(filename)}", styles['Normal']))
        story.append(Paragraph(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"Reviewed by: {safe_unicode_text(st.session_state.get('user_name', 'Unknown'))}", styles['Normal']))
        story.append(Paragraph(f"Total Violations: {len(violations)}", styles['Normal']))
        if violations:
            story.append(Paragraph(f"Content Language: {violations[0].get('detectedLanguage', 'Unknown')}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Summary by severity
        severity_counts = {}
        for v in violations:
            severity = v.get('severity', 'medium')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        story.append(Paragraph("VIOLATION SUMMARY BY SEVERITY", styles['Heading2']))
        for severity in ['critical', 'high', 'medium', 'low']:
            count = severity_counts.get(severity, 0)
            if count > 0:
                story.append(Paragraph(f"• {severity.upper()}: {count} violations", styles['Normal']))
        
        story.append(Spacer(1, 20))
        
        # Detailed violations with AI solutions
        story.append(Paragraph("DETAILED VIOLATIONS WITH AI SOLUTIONS", styles['Heading1']))
        story.append(Spacer(1, 10))
        
        detected_language = violations[0].get('detectedLanguage', 'Unknown') if violations else 'Unknown'
        
        # Custom styles for better Unicode handling
        violation_style = ParagraphStyle(
            'ViolationStyle',
            parent=styles['Normal'],
            leftIndent=20,
            rightIndent=20,
            spaceBefore=10,
            spaceAfter=10,
            borderWidth=1,
            borderColor=Color(0.8, 0.8, 0.8),
            backColor=Color(0.98, 0.98, 0.98),
            fontName='Helvetica'
        )
        
        for i, violation in enumerate(violations, 1):
            severity = violation.get('severity', 'medium')
            
            # Basic violation info
            violation_header = f"#{i}<br/>"
            violation_header += f"Type: {violation.get('violationType', 'Unknown')}<br/>"
            violation_header += f"Original Page: {violation.get('pageNumber', 'N/A')}<br/>"
            violation_header += f"Severity: {severity.upper()}<br/>"
            violation_header += f"Violation Text:<br/>"
            
            story.append(Paragraph(violation_header, violation_style))
            
            # Handle violation text separately with better Unicode support
            v_text = violation.get('violationText', 'N/A')
            safe_v_text = safe_unicode_text(v_text)
            
            # Create a separate paragraph for the violation text
            violation_text_style = ParagraphStyle(
                'ViolationTextStyle',
                parent=styles['Normal'],
                leftIndent=40,
                rightIndent=40,
                textColor=red,
                fontSize=10,
                spaceBefore=5,
                spaceAfter=5,
                fontName='Helvetica-Bold'
            )
            
            # Try to display the text, fallback to placeholder if Unicode fails
            try:
                story.append(Paragraph(f'"{safe_v_text}"', violation_text_style))
            except:
                story.append(Paragraph(f'"[Unicode text - {len(v_text)} characters in {detected_language}]"', violation_text_style))
            
            # Continue with explanation and solution
            explanation_text = f"Explanation: {safe_unicode_text(violation.get('explanation', 'N/A'))}<br/>"
            explanation_text += f"Suggested Action: {safe_unicode_text(violation.get('suggestedAction', 'N/A'))}<br/>"
            explanation_text += f"AI Solution ({detected_language}):<br/>"
            
            story.append(Paragraph(explanation_text, violation_style))
            
            # AI solution
            ai_solution = violation.get('aiSolution', 'N/A')
            safe_ai_solution = safe_unicode_text(ai_solution)
            
            ai_solution_style = ParagraphStyle(
                'AISolutionStyle',
                parent=styles['Normal'],
                leftIndent=40,
                rightIndent=40,
                textColor=Color(0, 0.6, 0),
                fontSize=10,
                spaceBefore=5,
                spaceAfter=5,
                fontName='Helvetica'
            )
            
            try:
                story.append(Paragraph(f'✓ {safe_ai_solution}', ai_solution_style))
            except:
                story.append(Paragraph(f'✓ [AI Solution in {detected_language} - {len(ai_solution)} characters]', ai_solution_style))
            
            # Status
            story.append(Paragraph("Status: PENDING REVIEW", styles['Normal']))
            story.append(Spacer(1, 10))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating violations report PDF: {e}")
        return None

def generate_highlighted_text_pdf(text, violations, filename):
    """Generate PDF with original text and highlighted violations - Unicode support"""
    if not PDF_AVAILABLE:
        return None
    
    try:
        setup_unicode_fonts()
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            spaceAfter=30,
            textColor=Color(0.2, 0.2, 0.6),
            alignment=1
        )
        
        story.append(Paragraph("hoichoi S&P COMPLIANCE - HIGHLIGHTED TEXT", title_style))
        story.append(Paragraph(f"Document: {filename}", styles['Normal']))
        story.append(Paragraph(f"Reviewed by: {st.session_state.get('user_name', 'Unknown')}", styles['Normal']))
        story.append(Paragraph(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Legend
        story.append(Paragraph("COLOR LEGEND", styles['Heading2']))
        legend_text = """
        <b>Background Colors indicate violation severity:</b><br/>
        🔴 <font color="red">Critical Severity</font> - Red highlighting, immediate attention required<br/>
        🟠 <font color="orange">High Severity</font> - Orange highlighting, high priority review<br/>
        🟡 <font color="#B8860B">Medium Severity</font> - Yellow highlighting, standard review<br/>
        🟣 <font color="purple">Low Severity</font> - Purple highlighting, minor issues<br/><br/>
        <b><font color="red">Text in red indicates the exact violation content</font></b> that triggered the S&P flag.
        """
        story.append(Paragraph(legend_text, styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Create violation mapping for highlighting
        violation_map = {}
        for violation in violations:
            v_text = violation.get('violationText', '').strip()
            severity = violation.get('severity', 'medium').lower()
            
            if v_text and len(v_text) >= 10:
                violation_map[v_text] = {
                    'severity': severity,
                    'type': violation.get('violationType', 'Unknown'),
                    'explanation': violation.get('explanation', '')
                }
        
        # Process text with highlighting
        story.append(Paragraph("DOCUMENT TEXT WITH HIGHLIGHTED VIOLATIONS", styles['Heading1']))
        story.append(Spacer(1, 10))
        
        # Split text into paragraphs
        paragraphs = text.split('\n')
        
        for para_text in paragraphs:
            if para_text.strip():
                # Check for original page markers
                if '=== ORIGINAL PAGE' in para_text:
                    page_match = re.search(r'=== ORIGINAL PAGE (\d+) ===', para_text)
                    if page_match:
                        page_num = page_match.group(1)
                        page_style = ParagraphStyle(
                            'PageMarker',
                            parent=styles['Heading3'],
                            textColor=Color(0.5, 0.5, 0.5),
                            alignment=1,
                            spaceBefore=20,
                            spaceAfter=10
                        )
                        story.append(Paragraph(f"— Original Page {page_num} —", page_style))
                    continue
                
                # Check for violations in this paragraph
                has_violation = False
                highlighted_text = para_text
                
                # Sort violations by length (longest first) to avoid overlapping replacements
                sorted_violations = sorted(violation_map.items(), key=lambda x: len(x[0]), reverse=True)
                
                for v_text, v_info in sorted_violations:
                    if v_text in highlighted_text:
                        severity = v_info['severity']
                        
                        # Color mapping for highlighting
                        if severity == 'critical':
                            bg_color = '#ffcdd2'  # Light red
                        elif severity == 'high':
                            bg_color = '#fff3e0'  # Light orange
                        elif severity == 'medium':
                            bg_color = '#fffde7'  # Light yellow
                        else:
                            bg_color = '#f3e5f5'  # Light purple
                        
                        # Create highlighted version
                        highlighted_replacement = f'<span style="background-color: {bg_color}; padding: 2px;"><font color="red"><b>{v_text}</b></font></span>'
                        highlighted_text = highlighted_text.replace(v_text, highlighted_replacement)
                        has_violation = True
                
                # Add paragraph with proper Unicode handling
                if has_violation:
                    highlighted_style = ParagraphStyle(
                        'HighlightedPara',
                        parent=styles['Normal'],
                        spaceBefore=6,
                        spaceAfter=6,
                        leftIndent=10,
                        rightIndent=10
                    )
                    story.append(create_unicode_paragraph(highlighted_text, highlighted_style))
                else:
                    if len(para_text) > 800:
                        para_text = para_text[:800] + "..."
                    story.append(create_unicode_paragraph(para_text, styles['Normal']))
                
                story.append(Spacer(1, 4))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating highlighted text PDF: {e}")
        return None

def create_violation_charts(violations):
    """Create visualization charts"""
    if not violations:
        return None, None
    
    df = pd.DataFrame(violations)
    
    # Severity distribution
    severity_counts = df['severity'].value_counts()
    severity_colors = {'critical': '#f44336', 'high': '#ff9800', 'medium': '#ffeb3b', 'low': '#9c27b0'}
    
    fig_severity = px.pie(
        values=severity_counts.values,
        names=severity_counts.index,
        title="Violation Severity Distribution",
        color=severity_counts.index,
        color_discrete_map=severity_colors
    )
    
    # Violation types
    type_counts = df['violationType'].value_counts().head(10)
    fig_types = px.bar(
        x=type_counts.values,
        y=type_counts.index,
        orientation='h',
        title="Top Violation Types",
        labels={'x': 'Count', 'y': 'Violation Type'}
    )
    
    return fig_severity, fig_types

def main():
    # Authentication check
    if not authenticate_user():
        return
    
    # Initialize session state to prevent resets
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'violations_data' not in st.session_state:
        st.session_state.violations_data = None
    if 'current_filename' not in st.session_state:
        st.session_state.current_filename = None
    
    # Custom CSS for authenticated app
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #ff6b6b, #4ecdc4);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .user-info {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #007bff;
    }
    .stDownloadButton > button {
        background-color: #007bff;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
    }
    .stDownloadButton > button:hover {
        background-color: #0056b3;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header with user info
    st.markdown("""
    <div class="main-header">
        <h1>🎬 hoichoi S&P Compliance Analyzer</h1>
        <p>Standards & Practices Content Review Platform</p>
        <p style="font-size: 0.9em; opacity: 0.9;">🔍 Aggressive Detection • 🌐 Enhanced Unicode Support • 24 Guidelines • Multi-language Ready</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar with user info and system status
    with st.sidebar:
        st.markdown(f"""
        <div class="user-info">
            <h3>👤 User Information</h3>
            <p><b>Name:</b> {st.session_state.get('user_name', 'Unknown')}</p>
            <p><b>Email:</b> {st.session_state.get('user_email', 'unknown@hoichoi.tv')}</p>
            <p><b>Role:</b> {'Admin' if st.session_state.get('is_admin', False) else 'Content Reviewer'}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        st.header("🔧 System Status & Unicode Support")
        
        # Unicode support status
        st.markdown("### 🌐 **Unicode & Multilingual Support**")
        
        # Check Unicode support
        try:
            test_bengali = "আমি বাংলায় কথা বলি"
            test_hindi = "मैं हिंदी में बात करता हूं"
            
            # Test safe text processing
            safe_bengali = safe_unicode_text(test_bengali)
            safe_hindi = safe_unicode_text(test_hindi)
            
            if safe_bengali and safe_hindi and len(safe_bengali) > 0 and len(safe_hindi) > 0:
                st.success("✅ Unicode Text Processing: Working")
                st.write(f"✓ Bengali test: {safe_bengali[:20]}...")
                st.write(f"✓ Hindi test: {safe_hindi[:20]}...")
            else:
                st.error("❌ Unicode Text Processing: Issues detected")
                
        except Exception as e:
            st.error(f"❌ Unicode Processing Error: {e}")
        
        # Check language detection
        try:
            lang_detect = detect_language("আমি বাংলায় কথা বলি")
            if lang_detect and lang_detect != "English":
                st.success(f"✅ Language Detection: Working (Detected: {lang_detect})")
            else:
                st.warning("⚠️ Language Detection: Using fallback method")
                # Try fallback detection
                fallback_lang = detect_language_fallback("আমি বাংলায় কথা বলি")
                st.write(f"Fallback detected: {fallback_lang}")
                
        except Exception as e:
            st.error(f"❌ Language Detection Error: {e}")
            
        # Test character analysis
        try:
            test_text = "আমি বাংলায় কথা বলি। मैं हिंदी में बात करता हूं।"
            unicode_count = sum(1 for char in test_text if ord(char) > 127)
            if unicode_count > 0:
                st.success(f"✅ Character Analysis: Working ({unicode_count} Unicode chars detected)")
            else:
                st.warning("⚠️ Character Analysis: No Unicode detected")
        except Exception as e:
            st.error(f"❌ Character Analysis Error: {e}")
        
        # System status
        st.markdown("### 🔧 **System Components**")
        if OPENAI_AVAILABLE:
            st.success("✅ OpenAI: Available")
        else:
            st.error("❌ OpenAI: Missing")
        
        if DOCX_AVAILABLE:
            st.success("✅ DOCX Processing: Available")
        else:
            st.error("❌ DOCX Processing: Missing")
        
        if PDF_EXTRACT_AVAILABLE:
            st.success("✅ PDF Processing: Available")
        else:
            st.error("❌ PDF Processing: Missing")
        
        if EXCEL_AVAILABLE:
            st.success("✅ Excel Reports: Available")
        else:
            st.error("❌ Excel Reports: Missing")
        
        if PDF_AVAILABLE:
            st.success("✅ PDF Generation: Available")
        else:
            st.error("❌ PDF Generation: Missing")
        
        # Unicode troubleshooting
        st.markdown("### 🔍 **Unicode Troubleshooting Guide**")
        with st.expander("Common Unicode Issues & Solutions"):
            st.markdown("""
            **Issue 1: Black blocks (■■■■■) in PDF reports**
            - **Cause**: PDF generation cannot handle Unicode characters
            - **Solution**: Use Unicode Test section to verify text handling
            - **Workaround**: Content will be analyzed correctly; only PDF display is affected
            
            **Issue 2: Language detection shows 'English' for non-English content**
            - **Cause**: OpenAI API issues or text preprocessing problems
            - **Solution**: Check API key configuration
            - **Workaround**: Manual language selection (feature to be added)
            
            **Issue 3: Violation text not showing properly**
            - **Cause**: Unicode encoding issues during text extraction
            - **Solution**: Ensure file is saved with proper encoding
            - **Workaround**: Use 'Paste Text' method for direct analysis
            
            **Issue 4: Missing characters in Excel reports**
            - **Cause**: Excel export not handling Unicode properly
            - **Solution**: Download and open in Excel with UTF-8 encoding
            - **Workaround**: Use PDF reports for better Unicode display
            """)
        
        # Performance recommendations
        st.markdown("### ⚡ **Performance Recommendations**")
        st.info("""
        **For Best Results:**
        - 📄 **File Size**: Keep scripts under 50 pages for optimal performance
        - 🔤 **Text Quality**: Ensure clean text extraction (avoid scanned PDFs)
        - 🌐 **Unicode**: Use Unicode Test section to verify text handling
        - 🔑 **API Key**: Ensure stable OpenAI API key configuration
        - 📊 **Reports**: Excel reports work best for data analysis, PDFs for visual review
        """)
        
        st.divider()
        
        if st.button("🔄 New Analysis", type="secondary"):
            # Reset session state for new analysis
            st.session_state.analysis_complete = False
            st.session_state.violations_data = None
            st.session_state.current_filename = None
            st.rerun()
        
        if st.button("🚪 Logout", type="secondary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # API Key check
    api_key = get_api_key()
    
    if not api_key:
        st.warning("⚠️ OpenAI API key not configured!")
        st.info("Please add OPENAI_API_KEY to Streamlit secrets or environment variables.")
        api_key = st.text_input("Enter OpenAI API Key", type="password", help="Your OpenAI API key for content analysis")
        if not api_key:
            st.stop()
    else:
        st.success("🔑 API Key configured")
    
    # Main tabs for upload vs paste
    tab1, tab2 = st.tabs(["📤 Upload Document", "📝 Paste Text"])
    
    with tab1:
        st.header("📤 Upload Document Analysis")
        st.markdown("**Upload your screenplay/script for comprehensive aggressive S&P compliance review.**")
        st.markdown("*🔍 Aggressive Detection: We analyze EVERYTHING - dialogues, scene descriptions, action lines, character names, props, settings, transitions*")
        st.markdown("*⚠️ Better to over-detect than miss violations - we flag anything potentially problematic*")
        st.markdown("*📋 Complete Coverage: All 24 S&P guidelines checked across entire script*")
        
        # Show current analysis if available
        if st.session_state.analysis_complete and st.session_state.violations_data:
            display_analysis_results(st.session_state.violations_data, st.session_state.current_filename)
        else:
            uploaded_file = st.file_uploader(
                "Choose a document file",
                type=['docx', 'pdf'],
                help="Upload a Microsoft Word document (.docx) or PDF file for S&P compliance analysis"
            )
            
            if uploaded_file is not None:
                file_type = uploaded_file.name.split('.')[-1].lower()
                st.success(f"✅ File uploaded: {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")
                
                if st.button("🔍 Start Analysis", type="primary", key="upload_analyze"):
                    # Extract text based on file type
                    with st.spinner(f"📄 Extracting text from {file_type.upper()} document..."):
                        if file_type == 'pdf':
                            text, pages_data = extract_text_from_pdf_bytes(uploaded_file.getvalue())
                        else:  # docx
                            text, pages_data = extract_text_from_docx_bytes(uploaded_file.getvalue())
                    
                    if not text:
                        st.error("❌ Failed to extract text from document")
                        return
                    
                    st.success(f"✅ Extracted {len(text):,} characters from {len(pages_data)} pages")
                    
                    # Analyze document
                    st.header("🤖 Analysis in Progress")
                    analysis = analyze_document(text, pages_data, api_key)
                    
                    # Store results in session state
                    st.session_state.violations_data = {
                        'violations': analysis.get('violations', []),
                        'summary': analysis.get('summary', {}),
                        'detected_language': analysis.get('detectedLanguage', 'Unknown'),
                        'text': text,
                        'pages_data': pages_data
                    }
                    st.session_state.current_filename = uploaded_file.name
                    st.session_state.analysis_complete = True
                    
                    # Display results
                    display_analysis_results(st.session_state.violations_data, uploaded_file.name)
    
    with tab2:
        st.header("📝 Paste Text Analysis")
        st.markdown("**Paste your screenplay content for comprehensive aggressive S&P compliance review.**")
        st.markdown("*🔍 Aggressive Detection: We examine every line for potential violations*")
        st.markdown("*⚠️ Thorough Analysis: Dialogues, scene descriptions, actions, character behavior, props, settings*")
        
        # Add Unicode test section
        with st.expander("🔧 Unicode Test & Debug"):
            st.markdown("**Test Unicode handling with sample Bengali text:**")
            
            sample_bengali = "আমি বাংলায় কথা বলি। এটি একটি পরীক্ষা।"
            sample_hindi = "मैं हिंदी में बात करता हूं। यह एक परीक्षा है।"
            
            test_text = st.text_area(
                "Test Unicode Text",
                value=sample_bengali,
                height=100,
                help="Paste any Unicode text here to test detection and handling"
            )
            
            if test_text:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Characters", len(test_text))
                with col2:
                    unicode_count = sum(1 for char in test_text if ord(char) > 127)
                    st.metric("Unicode Characters", unicode_count)
                with col3:
                    detected_lang = detect_language(test_text)
                    st.write(f"**Detected Language:** {detected_lang}")
                
                # Show character analysis
                st.markdown("**Character Analysis:**")
                char_analysis = {}
                for char in test_text:
                    if ord(char) > 127:
                        script_range = get_script_range(char)
                        char_analysis[script_range] = char_analysis.get(script_range, 0) + 1
                
                if char_analysis:
                    for script, count in char_analysis.items():
                        st.write(f"- {script}: {count} characters")
                
                # Test safe text handling
                st.markdown("**Safe Text Processing:**")
                safe_text = safe_unicode_text(test_text)
                st.text(f"Safe text: {safe_text}")
                
                # Test PDF generation
                if st.button("🔧 Test PDF Generation"):
                    try:
                        test_violations = [{
                            'violationText': test_text,
                            'violationType': 'Test_Unicode',
                            'explanation': 'Testing Unicode handling in PDF',
                            'suggestedAction': 'No action needed - this is a test',
                            'severity': 'low',
                            'pageNumber': 1,
                            'detectedLanguage': detected_lang,
                            'aiSolution': f"Test solution in {detected_lang}"
                        }]
                        
                        pdf_data = generate_violations_report_pdf(test_violations, "Unicode_Test.pdf")
                        if pdf_data:
                            st.success("✅ PDF generation successful!")
                            st.download_button(
                                label="📄 Download Test PDF",
                                data=pdf_data,
                                file_name="unicode_test.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("❌ PDF generation failed")
                    except Exception as e:
                        st.error(f"PDF test error: {e}")
        
        text_input = st.text_area(
            "Paste your screenplay/script content here",
            height=300,
            placeholder="Paste your screenplay content here for aggressive S&P compliance analysis...\n\nINT. LIVING ROOM - DAY\n\nRAJ sits on the sofa.\n\nRAJ\n(dialogue here)\nHello, how are you?\n\nPRIYA enters the room.\n\nPRIYA\nI'm fine, thanks.\n\nOur AI will analyze every element for potential violations!"
        )
        
        if text_input and st.button("🔍 Analyze Text", type="primary", key="paste_analyze"):
            # Create mock pages data for pasted text
            pages_data = [{"page_number": 1, "text": text_input, "original_page": 1}]
            
            # Analyze pasted text
            st.header("🤖 Analyzing Pasted Text")
            analysis = analyze_document(text_input, pages_data, api_key)
            
            violations = analysis.get('violations', [])
            detected_language = analysis.get('detectedLanguage', 'Unknown')
            
            # Display results for pasted text
            display_paste_analysis_results(violations, detected_language, text_input)
    
    # Footer with violation rules
    with st.expander("📋 S&P Violation Guidelines Reference (24 Aggressive Detection Rules)"):
        st.markdown("### 🎯 hoichoi Standards & Practices Guidelines")
        st.markdown("**Our system uses AGGRESSIVE DETECTION to find violations across your entire screenplay. We analyze every element thoroughly.**")
        st.markdown("---")
        
        st.markdown("### 🔍 **What We Analyze:**")
        st.markdown("""
        - **📝 Dialogues**: Every line of character speech
        - **🎬 Scene Descriptions**: Location setups, visual descriptions
        - **🎭 Action Lines**: Character movements, behaviors, actions
        - **👥 Character Names**: All character references and mentions
        - **🎪 Props & Settings**: Objects, locations, visual elements
        - **🎞️ Transitions**: Scene changes, cuts, fades, directions
        """)
        
        st.markdown("### ⚠️ **24 Violation Categories We Detect:**")
        
        for i, (rule_name, rule_data) in enumerate(VIOLATION_RULES.items(), 1):
            severity = rule_data['severity']
            if severity == "critical":
                st.error(f"🔴 **{i}. {rule_name.replace('_', ' ')}**")
            elif severity == "high":
                st.warning(f"🟠 **{i}. {rule_name.replace('_', ' ')}**")
            else:
                st.info(f"🟡 **{i}. {rule_name.replace('_', ' ')}**")
            
            st.markdown(f"**Description:** {rule_data['description']}")
            st.markdown(f"**Context:** {rule_data['context']}")
            st.markdown(f"**Keywords:** {', '.join(rule_data['keywords'])}")
            st.markdown("---")
        
        st.markdown("### 🎯 **Detection Philosophy**")
        st.markdown("""
        **✅ Better to Over-Detect than Miss Violations**
        - We flag anything that could potentially be problematic
        - When in doubt, we flag it for your review
        - Comprehensive analysis of all screenplay elements
        
        **🔍 Multi-Method Detection**
        - Keyword scanning for quick identification
        - Context analysis for subtle violations
        - Cultural sensitivity checks
        - Intent and meaning analysis
        
        **📋 Complete Coverage**
        - No element of your screenplay is ignored
        - Every dialogue line is examined
        - Every scene description is analyzed
        - Every action and prop is checked
        """)
        
        st.markdown("**📝 Result:** Comprehensive violation detection across your entire screenplay with detailed solutions for each issue found.")
    
    # Footer
    st.markdown("---")
    st.markdown(f"""
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        <p>🎬 hoichoi S&P Compliance System v2.1 | Enhanced Unicode Support | Reviewed by: {st.session_state.get('user_name', 'Unknown')}</p>
        <p>🔒 Secure access • 🔍 Aggressive violation detection • 🌐 Bengali/Hindi/Multi-language support • 📊 Comprehensive reporting</p>
    </div>
    """, unsafe_allow_html=True)

def display_analysis_results(violations_data, filename):
    """Display analysis results with aggressive detection feedback"""
    violations = violations_data['violations']
    summary = violations_data['summary']
    detected_language = violations_data['detected_language']
    text = violations_data['text']
    pages_data = violations_data['pages_data']
    
    # Results
    st.header("📊 Aggressive Analysis Results")
    
    # Show detection summary
    st.info(f"🔍 **Detection Summary**: Analyzed {summary.get('chunksAnalyzed', 0)} chunks, found violations in {summary.get('chunksWithViolations', 0)} chunks")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Violations Found", summary.get('totalViolations', 0))
    with col2:
        critical_count = len([v for v in violations if v.get('severity') == 'critical'])
        st.metric("🔴 Critical Issues", critical_count)
    with col3:
        st.metric("📄 Pages Analyzed", summary.get('totalPages', 0))
    with col4:
        st.metric("✅ Detection Rate", summary.get('successRate', '0%'))
    
    if violations:
        # Show detection effectiveness
        st.success(f"✅ **Aggressive Detection Successful**: Found {len(violations)} violations across your screenplay")
        
        # Charts
        st.subheader("📈 Violation Analytics")
        fig_severity, fig_types = create_violation_charts(violations)
        
        col1, col2 = st.columns(2)
        with col1:
            if fig_severity:
                st.plotly_chart(fig_severity, use_container_width=True)
        
        with col2:
            if fig_types:
                st.plotly_chart(fig_types, use_container_width=True)
        
        # Violation details with AI solutions
        st.subheader(f"🚨 Detected Violations with AI Solutions ({detected_language})")
        st.markdown("*Each violation detected through comprehensive script analysis*")
        
        for i, violation in enumerate(violations[:15]):  # Show first 15
            display_violation_details(violation, i+1, detected_language)
        
        if len(violations) > 15:
            st.info(f"Showing first 15 of {len(violations)} total violations detected")
        
        # Download Reports Section
        st.subheader("📥 Download Comprehensive Reports")
        
        # Generate reports (cached to avoid regeneration)
        if 'reports_generated' not in st.session_state:
            with st.spinner("Generating comprehensive reports..."):
                excel_data = generate_excel_report(violations, filename)
                violations_pdf = generate_violations_report_pdf(violations, filename)
                highlighted_pdf = generate_highlighted_text_pdf(text, violations, filename)
                
                st.session_state.reports_generated = {
                    'excel': excel_data,
                    'violations_pdf': violations_pdf,
                    'highlighted_pdf': highlighted_pdf
                }
        
        reports = st.session_state.reports_generated
        
        # Download buttons in columns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if reports['excel']:
                st.download_button(
                    label="📊 Excel Report",
                    data=reports['excel'],
                    file_name=f"{filename}_violations_detected.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="excel_download"
                )
        
        with col2:
            if reports['violations_pdf']:
                st.download_button(
                    label="📋 Violations Report",
                    data=reports['violations_pdf'],
                    file_name=f"{filename}_violations_report.pdf",
                    mime="application/pdf",
                    key="violations_download"
                )
        
        with col3:
            if reports['highlighted_pdf']:
                st.download_button(
                    label="🎨 Highlighted Script",
                    data=reports['highlighted_pdf'],
                    file_name=f"{filename}_highlighted_violations.pdf",
                    mime="application/pdf",
                    key="highlighted_download"
                )
        
        st.info(f"📋 **Reports Generated:** Excel with {len(violations)} violations, PDF violation summary, and highlighted script with flagged content")
    
    else:
        st.success("🎉 No violations detected! Your content appears to comply with S&P standards.")
        st.info("📋 **Note**: Our aggressive detection system analyzed your entire screenplay and found no violations against the 24 S&P guidelines.")
        st.balloons()

def display_violation_details(violation, index, detected_language):
    """Display individual violation details"""
    severity = violation.get('severity', 'low')
    
    if severity == 'critical':
        st.error(f"🔴 **{violation.get('violationType', 'Unknown')}** (Original Page {violation.get('pageNumber', 'N/A')})")
    elif severity == 'high':
        st.warning(f"🟠 **{violation.get('violationType', 'Unknown')}** (Original Page {violation.get('pageNumber', 'N/A')})")
    elif severity == 'medium':
        st.info(f"🟡 **{violation.get('violationType', 'Unknown')}** (Original Page {violation.get('pageNumber', 'N/A')})")
    else:
        st.success(f"🟢 **{violation.get('violationType', 'Unknown')}** (Original Page {violation.get('pageNumber', 'N/A')})")
    
    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.write("**🚨 Violated Text:**")
        st.markdown(f'<div style="background-color: #ffebee; padding: 10px; border-radius: 5px; border-left: 3px solid red;"><b style="color: red;">"{violation.get("violationText", "N/A")[:200]}..."</b></div>', unsafe_allow_html=True)
        st.write(f"**Issue:** {violation.get('explanation', 'N/A')}")
    
    with col_b:
        st.write(f"**🤖 AI Solution ({detected_language}):**")
        st.markdown(f'<div style="background-color: #e8f5e8; padding: 10px; border-radius: 5px; border-left: 3px solid green;"><b style="color: green;">"{violation.get("aiSolution", "N/A")}"</b></div>', unsafe_allow_html=True)
        st.write(f"**Action:** {violation.get('suggestedAction', 'N/A')}")
    
    st.divider()

def display_paste_analysis_results(violations, detected_language, text_input):
    """Display analysis results for pasted text"""
    st.header(f"📊 Analysis Results ({detected_language})")
    
    if violations:
        st.error(f"🚨 Found {len(violations)} violations in your text!")
        
        # Show violations with exact context and AI solutions
        st.subheader("🔍 Violated Content with AI Solutions")
        st.markdown("*Detected using hybrid analysis: keyword detection + contextual understanding*")
        
        for i, violation in enumerate(violations, 1):
            severity = violation.get('severity', 'low')
            
            # Color-coded violation display
            if severity == 'critical':
                st.error(f"**🔴 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
            elif severity == 'high':
                st.warning(f"**🟠 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
            elif severity == 'medium':
                st.info(f"**🟡 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
            else:
                st.success(f"**🟢 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
            
            # Show violated text with highlighting and AI solution
            violated_text = violation.get('violationText', '')
            ai_solution = violation.get('aiSolution', 'No solution available')
            
            col_a, col_b = st.columns([1, 1])
            
            with col_a:
                st.markdown("**🚨 Violated Text:**")
                # Create highlighted version
                highlighted_context = text_input
                if violated_text in highlighted_context:
                    if severity == 'critical':
                        color = "#ffcdd2"
                    elif severity == 'high':
                        color = "#fff3e0"
                    elif severity == 'medium':
                        color = "#fffde7"
                    else:
                        color = "#f3e5f5"
                    
                    highlighted_context = highlighted_context.replace(
                        violated_text,
                        f'<span style="background-color: {color}; padding: 2px 4px; border-radius: 3px; font-weight: bold; color: red;">{violated_text}</span>'
                    )
                
                st.markdown(f'<div style="background-color: #fafafa; padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto; border-left: 3px solid red;">{highlighted_context}</div>', unsafe_allow_html=True)
                st.markdown(f"**Why this violates S&P:** {violation.get('explanation', 'N/A')}")
            
            with col_b:
                st.markdown(f"**🤖 AI Solution ({detected_language}):**")
                st.markdown(f'<div style="background-color: #e8f5e8; padding: 10px; border-radius: 5px; border-left: 3px solid green;"><b style="color: green;">"{ai_solution}"</b></div>', unsafe_allow_html=True)
                st.markdown(f"**Suggested action:** {violation.get('suggestedAction', 'N/A')}")
                st.markdown(f"**Severity:** {severity.upper()}")
            
            st.divider()
        
        # Show severity summary
        st.subheader("📊 Violation Summary")
        severity_counts = {}
        for v in violations:
            severity = v.get('severity', 'medium')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🔴 Critical", severity_counts.get('critical', 0))
        with col2:
            st.metric("🟠 High", severity_counts.get('high', 0))
        with col3:
            st.metric("🟡 Medium", severity_counts.get('medium', 0))
        with col4:
            st.metric("🟢 Low", severity_counts.get('low', 0))
    
    else:
        st.success("🎉 No violations found! Your text appears to comply with S&P standards.")
        st.balloons()

if __name__ == "__main__":
    main()
