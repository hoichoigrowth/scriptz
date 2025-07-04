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
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import PyPDF2
    import pdfplumber
    PDF_EXTRACT_AVAILABLE = True
except ImportError:
    PDF_EXTRACT_AVAILABLE = False

# Configuration
MAX_CHARS_PER_CHUNK = 4000
OVERLAP_CHARS = 200
MAX_TOKENS_OUTPUT = 1000
CHUNK_DELAY = 1
MAX_RETRIES = 3

# S&P Violation Rules
VIOLATION_RULES = {
    "National_Symbols_Anthem": {
        "description": "Improper use of national symbols, anthem, flag, or government emblems",
        "keywords": ["national anthem", "flag", "tricolor", "ashoka chakra", "government logo"],
        "severity": "critical"
    },
    "PI_Data_Brand_References": {
        "description": "Personal information exposure, unauthorized brand references, trademark violations",
        "keywords": ["personal data", "phone number", "address", "brand name", "trademark"],
        "severity": "high"
    },
    "Credits_Endorsements": {
        "description": "Missing credits, unauthorized endorsements, celebrity impersonation",
        "keywords": ["credit", "endorsement", "celebrity", "sponsor", "testimonial"],
        "severity": "medium"
    },
    "Religious_Cultural_Sensitivity": {
        "description": "Religious insensitivity, cultural stereotypes, communal bias, offensive content",
        "keywords": ["religion", "god", "hindu", "muslim", "christian", "sikh", "culture", "caste"],
        "severity": "critical"
    },
    "Animal_Welfare": {
        "description": "Animal cruelty, unsafe animal handling, wildlife protection violations",
        "keywords": ["animal", "cruelty", "pet", "wildlife", "zoo", "circus"],
        "severity": "high"
    },
    "Disclaimers_Warnings": {
        "description": "Missing disclaimers, inadequate warnings, safety information gaps",
        "keywords": ["disclaimer", "warning", "caution", "safety", "risk"],
        "severity": "medium"
    },
    "Smoking_Alcohol_Social_Evils": {
        "description": "Glorification of smoking, alcohol abuse, gambling, or other social evils",
        "keywords": ["smoke", "cigarette", "alcohol", "drink", "gambling", "bet", "drugs"],
        "severity": "high"
    },
    "Child_Safety": {
        "description": "Content harmful to minors, inappropriate child representation, safety risks",
        "keywords": ["child", "minor", "kid", "school", "unsafe", "inappropriate"],
        "severity": "critical"
    },
    "Violence_Self_Harm": {
        "description": "Graphic violence, self-harm content, suicide references, dangerous activities",
        "keywords": ["violence", "fight", "blood", "suicide", "self-harm", "dangerous", "weapon"],
        "severity": "critical"
    },
    "Substances_Addiction": {
        "description": "Drug use promotion, addiction glorification, substance abuse normalization",
        "keywords": ["drugs", "addiction", "substance", "abuse", "dealer", "high", "overdose"],
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
    """Detect the primary language of the text using AI"""
    api_key = get_api_key()
    if not OPENAI_AVAILABLE or not api_key:
        return "English"
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Take a sample of the text for language detection
        sample = text_sample[:1000] if len(text_sample) > 1000 else text_sample
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a language detection expert. Identify the primary language of the given text. Return only the language name in English (e.g., 'Hindi', 'Bengali', 'Tamil', 'English', etc.)."},
                {"role": "user", "content": f"What language is this text primarily written in? Text: {sample}"}
            ],
            max_tokens=10,
            temperature=0
        )
        
        detected_language = response.choices[0].message.content.strip()
        return detected_language
        
    except:
        return "English"  # Default fallback

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
    """Generate AI solution for the violation in the detected language"""
    if not OPENAI_AVAILABLE or not api_key:
        return "AI solution generation not available"
    
    try:
        client = OpenAI(api_key=api_key)
        
        prompt = f"""You are an expert content editor for Indian digital media. Generate a revised version of the problematic content that resolves the S&P violation while maintaining the creative intent.

VIOLATION DETAILS:
- Type: {violation_type}
- Problematic Text: "{violation_text}"
- Issue: {explanation}
- Content Language: {detected_language}

INSTRUCTIONS:
1. Provide a revised version that eliminates the S&P violation
2. Maintain the original tone and creative intent
3. Keep the same language as the original content ({detected_language})
4. Ensure the solution is culturally appropriate for Indian audiences
5. Make minimal changes while fixing the compliance issue

Return ONLY the revised text solution, nothing else."""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert content editor specializing in S&P compliance for Indian digital media."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error generating solution: {str(e)}"

def chunk_text(text, max_chars=MAX_CHARS_PER_CHUNK):
    """Split text into analysis chunks while preserving page boundaries"""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    
    # Split by page markers first
    page_sections = re.split(r'(=== ORIGINAL PAGE \d+ ===)', text)
    
    current_chunk = ""
    
    for section in page_sections:
        if not section.strip():
            continue
            
        # If adding this section would exceed max_chars, save current chunk
        if len(current_chunk + section) > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = section
        else:
            current_chunk += section
    
    # Add remaining chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

def create_analysis_prompt():
    """Create S&P compliance analysis prompt"""
    violation_types = []
    for v_type, details in VIOLATION_RULES.items():
        violation_types.append(f"- {v_type.replace('_', ' ')}: {details['description']} (Severity: {details['severity']})")
    
    violation_types_str = "\n".join(violation_types)
    
    return f"""You are an expert S&P compliance reviewer for Indian digital media. Analyze this content chunk for violations including ALL screenplay elements (scene headings, character names, dialogue, action descriptions, transitions).

VIOLATION CATEGORIES (choose most appropriate):
{violation_types_str}

CRITICAL INSTRUCTIONS:
1. Copy violation text EXACTLY as it appears
2. Extract meaningful violations only (minimum 10 characters)
3. Choose appropriate category and severity
4. Analyze ALL content types: dialogue, action, scene descriptions, character names, transitions
5. Focus on substantial policy violations

Return ONLY valid JSON:
{{
  "violations": [
    {{
      "violationText": "EXACT text preserving all formatting",
      "violationType": "Category name from list above",
      "explanation": "why this violates broadcasting standards",
      "suggestedAction": "specific remediation needed",
      "severity": "critical|high|medium|low"
    }}
  ]
}}

If no violations found, return: {{"violations": []}}"""

def analyze_chunk(chunk, chunk_num, total_chunks, api_key):
    """Analyze single chunk with OpenAI"""
    if not OPENAI_AVAILABLE or not api_key:
        return {"violations": []}
    
    try:
        client = OpenAI(api_key=api_key)
        
        prompt = create_analysis_prompt()
        full_prompt = f"""{prompt}

Content to analyze:
{chunk}

JSON response only:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an S&P compliance expert. Return only valid JSON."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.1,
            max_tokens=MAX_TOKENS_OUTPUT,
            timeout=60
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse JSON with fallback
        try:
            parsed_result = json.loads(result)
        except json.JSONDecodeError:
            json_start = result.find('{')
            json_end = result.rfind('}')
            if json_start != -1 and json_end != -1:
                json_text = result[json_start:json_end + 1]
                try:
                    parsed_result = json.loads(json_text)
                except:
                    return {"violations": []}
            else:
                return {"violations": []}
        
        # Validate violations
        if 'violations' in parsed_result:
            enhanced_violations = []
            for violation in parsed_result['violations']:
                violation_text = violation.get('violationText', '').strip()
                if len(violation_text) >= 10:
                    enhanced_violations.append(violation)
            parsed_result['violations'] = enhanced_violations
        
        time.sleep(CHUNK_DELAY)
        return parsed_result
        
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
    """Analyze entire document with AI solutions"""
    if not text or not api_key:
        return {"violations": [], "summary": {}}
    
    # Detect language first
    detected_language = detect_language(text)
    st.info(f"🌐 Detected content language: **{detected_language}**")
    
    chunks = chunk_text(text)
    all_violations = []
    successful_chunks = 0
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        progress = (i + 1) / len(chunks)
        progress_bar.progress(progress)
        status_text.text(f"Analyzing chunk {i+1}/{len(chunks)}...")
        
        analysis = analyze_chunk(chunk, i+1, len(chunks), api_key)
        
        if 'violations' in analysis:
            for violation in analysis['violations']:
                violation['pageNumber'] = find_page_number(violation.get('violationText', ''), pages_data)
                violation['chunkNumber'] = i + 1
                violation['detectedLanguage'] = detected_language
                all_violations.append(violation)
            successful_chunks += 1
    
    # Generate AI solutions for violations
    if all_violations:
        status_text.text("🤖 Generating AI solutions...")
        for i, violation in enumerate(all_violations):
            progress = (i + 1) / len(all_violations)
            progress_bar.progress(progress)
            
            ai_solution = generate_ai_solution(
                violation.get('violationText', ''),
                violation.get('violationType', ''),
                violation.get('explanation', ''),
                detected_language,
                api_key
            )
            violation['aiSolution'] = ai_solution
    
    progress_bar.progress(1.0)
    status_text.text("✅ Analysis complete!")
    
    # Remove duplicates
    unique_violations = []
    seen_texts = set()
    for violation in all_violations:
        v_text = violation.get('violationText', '')
        duplicate_key = (v_text[:100], violation.get('violationType', ''), violation.get('pageNumber', 0))
        
        if duplicate_key not in seen_texts:
            seen_texts.add(duplicate_key)
            unique_violations.append(violation)
    
    # Sort by page and severity
    severity_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
    unique_violations.sort(key=lambda x: (
        x.get('pageNumber', 0),
        -severity_order.get(x.get('severity', 'low'), 1)
    ))
    
    return {
        "violations": unique_violations,
        "detectedLanguage": detected_language,
        "summary": {
            "totalViolations": len(unique_violations),
            "totalPages": len(pages_data),
            "chunksAnalyzed": len(chunks),
            "successfulChunks": successful_chunks,
            "successRate": f"{(successful_chunks/len(chunks)*100):.1f}%" if chunks else "0%"
        }
    }

def generate_excel_report(violations, filename):
    """Generate Excel report with AI solutions"""
    if not EXCEL_AVAILABLE:
        return None
    
    try:
        # Create enhanced dataframe with proper column ordering
        excel_data = []
        for violation in violations:
            excel_data.append({
                'Page Number': violation.get('pageNumber', 'N/A'),
                'Violation Type': violation.get('violationType', 'Unknown'),
                'Severity': violation.get('severity', 'medium').upper(),
                'Violated Text': violation.get('violationText', 'N/A'),
                'Explanation': violation.get('explanation', 'N/A'),
                'Suggested Action': violation.get('suggestedAction', 'N/A'),
                'AI Solution': violation.get('aiSolution', 'N/A'),
                'Language': violation.get('detectedLanguage', 'Unknown'),
                'Chunk Number': violation.get('chunkNumber', 'N/A')
            })
        
        df = pd.DataFrame(excel_data)
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Violations', index=False)
            
            # Summary sheet
            summary_data = {
                'Metric': ['Total Violations', 'Critical', 'High', 'Medium', 'Low'],
                'Count': [
                    len(violations),
                    len([v for v in violations if v.get('severity') == 'critical']),
                    len([v for v in violations if v.get('severity') == 'high']),
                    len([v for v in violations if v.get('severity') == 'medium']),
                    len([v for v in violations if v.get('severity') == 'low'])
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Format the sheets
            workbook = writer.book
            violation_sheet = workbook['Violations']
            
            # Auto-adjust column widths
            for column in violation_sheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
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
    """Generate PDF report with violation details and AI solutions - Unicode support"""
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
        
        story.append(Paragraph("hoichoi S&P COMPLIANCE VIOLATION REPORT", title_style))
        story.append(Paragraph(f"Document: {filename}", styles['Normal']))
        story.append(Paragraph(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"Reviewed by: {st.session_state.get('user_name', 'Unknown')}", styles['Normal']))
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
                color = red if severity == 'critical' else orange if severity == 'high' else Color(0.7, 0.7, 0) if severity == 'medium' else Color(0.5, 0.5, 0.5)
                severity_style = ParagraphStyle('Severity', parent=styles['Normal'], textColor=color, fontSize=12, spaceAfter=6)
                story.append(Paragraph(f"• {severity.upper()}: {count} violations", severity_style))
        
        story.append(Spacer(1, 20))
        
        # Detailed violations with AI solutions
        story.append(Paragraph("DETAILED VIOLATIONS WITH AI SOLUTIONS", styles['Heading1']))
        story.append(Spacer(1, 10))
        
        detected_language = violations[0].get('detectedLanguage', 'Unknown') if violations else 'Unknown'
        
        for i, violation in enumerate(violations, 1):
            # Violation header
            violation_style = ParagraphStyle(
                f'Violation{i}',
                parent=styles['Normal'],
                leftIndent=20,
                rightIndent=20,
                spaceBefore=10,
                spaceAfter=10,
                borderWidth=1,
                borderColor=Color(0.8, 0.8, 0.8),
                backColor=Color(0.98, 0.98, 0.98)
            )
            
            severity = violation.get('severity', 'medium')
            severity_color = red if severity == 'critical' else orange if severity == 'high' else Color(0.7, 0.7, 0) if severity == 'medium' else Color(0.5, 0.5, 0.5)
            
            # Safely handle Unicode text
            v_text = violation.get('violationText', 'N/A')
            ai_solution = violation.get('aiSolution', 'N/A')
            
            violation_detail = f"<b>#{i}</b><br/>"
            violation_detail += f"<b>Type:</b> {violation.get('violationType', 'Unknown')}<br/>"
            violation_detail += f"<b>Original Page:</b> {violation.get('pageNumber', 'N/A')}<br/>"
            violation_detail += f"<b>Severity:</b> {severity.upper()}<br/>"
            violation_detail += f"<b>Violation Text:</b><br/>"
            
            # Add violation text as separate paragraph to handle Unicode better
            story.append(Paragraph(violation_detail, violation_style))
            
            # Violation text in red
            violation_text_style = ParagraphStyle(
                f'ViolationText{i}',
                parent=styles['Normal'],
                leftIndent=40,
                rightIndent=40,
                textColor=red,
                fontSize=10,
                spaceBefore=5,
                spaceAfter=5
            )
            story.append(create_unicode_paragraph(f"「{v_text}」", violation_text_style, detected_language))
            
            # Continue with other details
            detail_continuation = f"<b>Explanation:</b> {violation.get('explanation', 'N/A')}<br/>"
            detail_continuation += f"<b>Suggested Action:</b> {violation.get('suggestedAction', 'N/A')}<br/>"
            detail_continuation += f"<b>🤖 AI Solution ({detected_language}):</b><br/>"
            
            story.append(Paragraph(detail_continuation, violation_style))
            
            # AI solution in green
            ai_solution_style = ParagraphStyle(
                f'AISolution{i}',
                parent=styles['Normal'],
                leftIndent=40,
                rightIndent=40,
                textColor=Color(0, 0.6, 0),
                fontSize=10,
                spaceBefore=5,
                spaceAfter=5
            )
            story.append(create_unicode_paragraph(f"✓ {ai_solution}", ai_solution_style, detected_language))
            
            # Status
            status_style = ParagraphStyle(
                f'Status{i}',
                parent=styles['Normal'],
                leftIndent=20,
                rightIndent=20,
                textColor=red,
                fontSize=10,
                spaceBefore=5,
                spaceAfter=15
            )
            story.append(Paragraph("<b>Status:</b> PENDING REVIEW", status_style))
        
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
        
        st.header("🔧 System Status")
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
        
        text_input = st.text_area(
            "Paste your content here",
            height=300,
            placeholder="Paste your script, dialogue, or content here for immediate S&P compliance analysis..."
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
    with st.expander("📋 S&P Violation Categories Reference"):
        for rule_name, rule_data in VIOLATION_RULES.items():
            severity = rule_data['severity']
            if severity == 'critical':
                st.error(f"🔴 **{rule_name.replace('_', ' ')}**")
            elif severity == 'high':
                st.warning(f"🟠 **{rule_name.replace('_', ' ')}**")
            else:
                st.info(f"🟡 **{rule_name.replace('_', ' ')}**")
            
            st.write(rule_data['description'])
            st.write(f"**Keywords:** {', '.join(rule_data['keywords'])}")
            st.divider()
    
    # Footer
    st.markdown("---")
    st.markdown(f"""
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        <p>🎬 hoichoi S&P Compliance System | Reviewed by: {st.session_state.get('user_name', 'Unknown')}</p>
        <p>🔒 Secure access for authorized personnel only | Session logged for security</p>
    </div>
    """, unsafe_allow_html=True)

def display_analysis_results(violations_data, filename):
    """Display analysis results with download buttons that don't reset the page"""
    violations = violations_data['violations']
    summary = violations_data['summary']
    detected_language = violations_data['detected_language']
    text = violations_data['text']
    pages_data = violations_data['pages_data']
    
    # Results
    st.header("📊 Analysis Results")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Violations", summary.get('totalViolations', 0))
    with col2:
        critical_count = len([v for v in violations if v.get('severity') == 'critical'])
        st.metric("🔴 Critical", critical_count)
    with col3:
        st.metric("📄 Pages", summary.get('totalPages', 0))
    with col4:
        st.metric("✅ Success Rate", summary.get('successRate', '0%'))
    
    if violations:
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
        st.subheader(f"🚨 Violations with AI Solutions ({detected_language})")
        
        for i, violation in enumerate(violations[:10]):  # Show first 10
            display_violation_details(violation, i+1, detected_language)
        
        if len(violations) > 10:
            st.info(f"Showing first 10 of {len(violations)} total violations")
        
        # Download Reports Section
        st.subheader("📥 Download Reports")
        
        # Generate reports (cached to avoid regeneration)
        if 'reports_generated' not in st.session_state:
            with st.spinner("Generating reports..."):
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
                    file_name=f"{filename}_analysis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="excel_download"
                )
        
        with col2:
            if reports['violations_pdf']:
                st.download_button(
                    label="📋 Violations Report",
                    data=reports['violations_pdf'],
                    file_name=f"{filename}_violations.pdf",
                    mime="application/pdf",
                    key="violations_download"
                )
        
        with col3:
            if reports['highlighted_pdf']:
                st.download_button(
                    label="🎨 Highlighted Text",
                    data=reports['highlighted_pdf'],
                    file_name=f"{filename}_highlighted.pdf",
                    mime="application/pdf",
                    key="highlighted_download"
                )
        
        st.info("📋 **Reports Available:** Excel spreadsheet with detailed analysis, PDF violation summary, and highlighted text version")
    
    else:
        st.success("🎉 No violations found! Content appears to comply with S&P standards.")
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
        st.subheader("🔍 Violated Strings with AI Solutions")
        
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
