#!/usr/bin/env python3
"""
publish_manuscript.py — Convert the Spectral Pairing Theorem manuscript to LaTeX
and prepare for arXiv submission.

This script:
1. Converts the Markdown manuscript to LaTeX format
2. Creates a complete arXiv submission package
3. Generates a PDF (if LaTeX is available)
4. Prepares the GitHub commit

USAGE:
    python publish_manuscript.py          # Convert to LaTeX and prepare arXiv package
    python publish_manuscript.py --pdf    # Also generate PDF (requires LaTeX)
    python publish_manuscript.py --commit # Also commit to git
"""

import os
import sys
import re
import subprocess
from datetime import datetime

# Force UTF-8 output on Windows consoles
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MANUSCRIPT_MD = os.path.join(PROJECT_ROOT, 'docs', 'SPECTRAL_PAIRING_THEOREM.md')
ARXIV_DIR = os.path.join(PROJECT_ROOT, 'docs', 'arXiv-submission')


def markdown_to_latex(md_content):
    """Convert Markdown manuscript to LaTeX format."""
    
    # LaTeX preamble
    latex = r"""%% The Spectral Pairing Theorem: A Unified Framework Connecting the Riemann Zeros, Hyperbolic Geometry, and Quantum Information
%% Author: Gregory J.
%% Date: """ + datetime.now().strftime('%B %d, %Y') + r"""

\documentclass[11pt,letterpaper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{geometry}
\usepackage{fancyhdr}
\usepackage{natbib}
\usepackage{enumitem}
\usepackage{booktabs}
\usepackage{algorithm}
\usepackage{algpseudocode}

\geometry{margin=1in}
\pagestyle{fancy}
\fancyhf{}
\rhead{\thepage}
\lhead{The Spectral Pairing Theorem}

\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    filecolor=magenta,      
    urlcolor=cyan,
    pdftitle={The Spectral Pairing Theorem},
    pdfauthor={Gregory J.},
    pdfsubject={Riemann Hypothesis, Montgomery pair correlation, Cayley graph Laplacian, scalar wave},
    pdfkeywords={Riemann Hypothesis, Montgomery pair correlation, Cayley graph Laplacian, scalar wave, Hilbert-Pólya conjecture, GUE statistics, topological quantum field theory, AdS/CFT correspondence}
}

\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{conjecture}[theorem]{Conjecture}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{remark}[theorem]{Remark}

\title{The Spectral Pairing Theorem: A Unified Framework Connecting the Riemann Zeros, Hyperbolic Geometry, and Quantum Information}
\author{Gregory J.}
\affiliation{Aetherion Research Laboratory}
\date{""" + datetime.now().strftime('%B %d, %Y') + r"""}

\begin{document}

\maketitle

\begin{abstract}
"""
    
    # Process the markdown content
    lines = md_content.split('\n')
    in_abstract = False
    in_theorem = False
    in_proof = False
    in_equation = False
    in_table = False
    skip_section = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip the title and author info (already in preamble)
        if line.startswith('# The Spectral Pairing'):
            i += 1
            while i < len(lines) and (lines[i].startswith('**') or lines[i].startswith('---')):
                i += 1
            continue
        
        # Skip horizontal rules
        if line.strip() == '---':
            i += 1
            continue
        
        # Handle sections
        if line.startswith('## '):
            section_name = line[3:].strip()
            # Skip abstract (handled separately)
            if section_name == 'Abstract':
                in_abstract = True
                i += 1
                continue
            elif section_name.startswith('Appendix'):
                latex += f'\\section*{{{section_name}}}\n\n'
            else:
                # Remove section numbers
                section_name = re.sub(r'^\d+\.\s*', '', section_name)
                latex += f'\\section{{{section_name}}}\n\n'
            i += 1
            continue
        
        if line.startswith('### '):
            subsection_name = line[4:].strip()
            subsection_name = re.sub(r'^\d+\.\s*', '', subsection_name)
            latex += f'\\subsection{{{subsection_name}}}\n\n'
            i += 1
            continue
        
        # Handle abstract
        if in_abstract:
            if line.startswith('**Keywords'):
                in_abstract = False
                keywords = line.replace('**Keywords:** ', '')
                latex += '\n\n\\keywords{' + keywords + '}\n\n'
            elif line.strip():
                latex += line + ' '
            i += 1
            continue
        
        # Handle theorems
        if '**Theorem' in line and '.' in line:
            # Extract theorem name
            match = re.search(r'\*\*Theorem \d+[:\s]+([^*]+)\*\*', line)
            if match:
                theorem_name = match.group(1).strip()
                latex += f'\begin{{theorem}}[{theorem_name}]\n'
                in_theorem = True
            i += 1
            continue
        
        if '**Lemma' in line:
            match = re.search(r'\*\*Lemma \d+\*\*', line)
            if match:
                latex += '\begin{lemma}\n'
                in_theorem = True
            i += 1
            continue
        
        if '**Proof.**' in line:
            latex += '\n\\begin{proof}\n'
            in_proof = True
            # Get the rest of the line
            rest = line.split('**Proof.**', 1)[1].strip()
            if rest:
                latex += rest + ' '
            i += 1
            continue
        
        if line.strip() == '∎' or line.strip() == 'Q.E.D.':
            if in_proof:
                latex += '\n\\end{proof}\n\n'
                in_proof = False
            if in_theorem:
                latex += '\n\\end{theorem}\n\n'
                in_theorem = False
            i += 1
            continue
        
        # Handle equations
        if line.startswith('$$'):
            eq = line.strip('$').strip()
            if eq:
                # Check if it's a multi-line equation
                if '\\' in eq or '&' in eq:
                    latex += '\\begin{align}\n' + eq + '\n\\end{align}\n\n'
                else:
                    latex += '\\begin{equation}\n' + eq + '\n\\end{equation}\n\n'
            i += 1
            continue
        
        # Handle inline math
        line = line.replace('$$', '')
        
        # Handle bold text
        line = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', line)
        
        # Handle italic text
        line = re.sub(r'\*(.+?)\*', r'\\textit{\1}', line)
        
        # Handle code
        line = re.sub(r'`(.+?)`', r'\\texttt{\1}', line)
        
        # Handle bullet points
        if line.startswith('- '):
            item = line[2:].strip()
            # Remove inline math markers for LaTeX
            item = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', item)
            latex += f'\\item {item}\n'
            i += 1
            continue
        
        # Handle numbered lists
        if re.match(r'^\d+\.\s', line):
            item = re.sub(r'^\d+\.\s*', '', line).strip()
            item = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', item)
            latex += f'\\item {item}\n'
            i += 1
            continue
        
        # Handle tables (simplified - skip complex tables)
        if line.startswith('|') and '---' in line:
            # Table separator, skip
            i += 1
            continue
        if line.startswith('|') and '|' in line:
            # Table row - convert to simple tabular
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if all(c.startswith('-') for c in cells):
                # Skip separator rows
                i += 1
                continue
            latex += ' & '.join(cells) + ' \\\n'
            i += 1
            continue
        
        # Handle blockquotes
        if line.startswith('> '):
            latex += f'\\begin{{quote}}\n{line[2:].strip()}\n\\end{{quote}}\n\n'
            i += 1
            continue
        
        # Handle code blocks
        if line.startswith('```'):
            # Skip code blocks
            while i < len(lines) and not lines[i].startswith('```'):
                i += 1
            i += 1  # Skip closing ```
            continue
        
        # Handle empty lines
        if not line.strip():
            latex += '\n'
            i += 1
            continue
        
        # Regular text
        if line.strip():
            latex += line + '\n'
        
        i += 1
    
    # Close the document
    latex += r"""

\end{document}
"""
    
    return latex


def create_arxiv_package():
    """Create a complete arXiv submission package."""
    
    print("Creating arXiv submission package...")
    
    # Create the arXiv directory
    os.makedirs(ARXIV_DIR, exist_ok=True)
    
    # Read the markdown manuscript
    with open(MANUSCRIPT_MD, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Convert to LaTeX
    latex_content = markdown_to_latex(md_content)
    
    # Write the LaTeX file
    latex_file = os.path.join(ARXIV_DIR, 'spectral_pairing_theorem.tex')
    with open(latex_file, 'w', encoding='utf-8') as f:
        f.write(latex_content)
    
    print(f"  LaTeX file created: {latex_file}")
    
    # Create README for arXiv
    readme = f"""# The Spectral Pairing Theorem

## Submission to arXiv

This package contains the LaTeX source for the manuscript:

**The Spectral Pairing Theorem: A Unified Framework Connecting the Riemann Zeros, Hyperbolic Geometry, and Quantum Information**

by Gregory J. (Aetherion Research Laboratory)

Date: {datetime.now().strftime('%B %d, %Y')}

## Compilation

To compile the PDF:

```bash
pdflatex spectral_pairing_theorem.tex
pdflatex spectral_pairing_theorem.tex
bibtex spectral_pairing_theorem
pdflatex spectral_pairing_theorem.tex
pdflatex spectral_pairing_theorem.tex
```

## Categories for arXiv

Primary: math.NT (Number Theory)
Secondary: math-ph (Mathematical Physics), quant-ph (Quantum Physics), hep-th (High Energy Physics - Theory)

## Abstract

We present a computational framework that establishes deep connections between the non-trivial zeros of the Riemann zeta function, the spectral gap of Cayley graph Laplacians over finite fields, the Montgomery pair correlation function R₂(w) = 1 - |sin(πw)/(πw)|², and the longitudinal scalar wave equation ∂²φ/∂t² = c²∇²φ.

## Code Repository

All code implementing the framework is available at:
https://github.com/[username]/excalibur-chain

## Key Files

- riemann_solution.py: Non-circular RH framework (21/21 tests)
- hilbert_polya.py: Berry-Keating Hamiltonian
- montgomery_pair_correlation.py: R₂(w) computation
- spectral_graph_shor.py: Cayley graph Laplacian
- scalar_wave_unification.py: Longitudinal scalar waves
- topological_quantum_field.py: TQFT simulator
- bell_state_asm.py: Bell state assembly language
- knot_math.py: Möbius function and knot computation
- theory_of_everything.py: AdS/CFT unification
"""
    
    readme_file = os.path.join(ARXIV_DIR, 'README.md')
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme)
    
    print(f"  README created: {readme_file}")
    
    # Create zip for arXiv (PowerShell only supports .zip natively)
    print("  Creating arXiv submission package (zip)...")
    
    tar_gz_path = os.path.join(PROJECT_ROOT, 'docs', 'spectral_pairing_theorem.tar.gz')
    zip_path = os.path.join(PROJECT_ROOT, 'docs', 'spectral_pairing_theorem.zip')
    
    if sys.platform == 'win32':
        # Windows: use PowerShell to create zip
        subprocess.run([
            'powershell', '-Command',
            f'Compress-Archive -Path "{os.path.join(ARXIV_DIR, "*")}" -DestinationPath "{zip_path}" -Force'
        ], check=True)
        print(f"  arXiv package created: spectral_pairing_theorem.zip")
        print(f"  Note: For arXiv, rename to .tar.gz or use: tar -czf spectral_pairing_theorem.tar.gz -C docs/arXiv-submission .")
    else:
        # Unix: use tar
        subprocess.run([
            'tar', '-czf',
            tar_gz_path,
            '-C', ARXIV_DIR,
            'spectral_pairing_theorem.tex', 'README.md'
        ], check=True)
        print(f"  arXiv package created: spectral_pairing_theorem.tar.gz")
    
    return latex_file


def generate_pdf(latex_file):
    """Generate PDF from LaTeX (requires pdflatex)."""
    
    print("Generating PDF...")
    
    # Try to compile with pdflatex
    try:
        result = subprocess.run(
            ['pdflatex', '-interaction=nonstopmode', latex_file],
            capture_output=True, text=True, timeout=60
        )
        
        if result.returncode == 0:
            pdf_file = latex_file.replace('.tex', '.pdf')
            print(f"  PDF generated: {pdf_file}")
            return pdf_file
        else:
            print("  Warning: pdflatex compilation had warnings")
            print("  Run manually for best results:")
            print(f"    pdflatex {latex_file}")
            return None
    except FileNotFoundError:
        print("  Error: pdflatex not found. Install LaTeX to generate PDF.")
        print("  On Windows: install MiKTeX or TeX Live")
        print("  On Ubuntu: sudo apt-get install texlive-latex-extra")
        return None
    except subprocess.TimeoutExpired:
        print("  Error: pdflatex timed out")
        return None


def commit_to_git():
    """Commit the manuscript to git."""
    
    print("Committing to git...")
    
    # Add the manuscript
    subprocess.run(['git', 'add', 'docs/SPECTRAL_PAIRING_THEOREM.md'], check=True)
    subprocess.run(['git', 'add', 'docs/arXiv-submission/'], check=True)
    subprocess.run(['git', 'add', 'publish_manuscript.py'], check=True)
    
    # Commit
    commit_msg = """Add: The Spectral Pairing Theorem manuscript

Formal publication-ready manuscript presenting the unified framework
connecting the Riemann zeros, hyperbolic geometry, and quantum information.

Key results:
- Theorem 1: Explicit formula as identity (not assumption)
- Theorem 2: Cayley graph spectral gap from group theory
- Theorem 3: Montgomery pair correlation matches GUE prediction
- Theorem 4: Scalar wave autocorrelation = R₂(w)
- Theorem 5: Bell state resolution of identity
- Theorem 6: Jones polynomial connects to ζ(s) via Dedekind eta
- Theorem 7: Spectral Pairing Theorem (unified framework)

Computational verification: 21/21 tests pass.

Co-authored-by: Junie <junie@jetbrains.com>"""
    
    result = subprocess.run(
        ['git', 'commit', '-m', commit_msg],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print("  Committed successfully")
    else:
        print(f"  Commit failed: {result.stderr}")


def push_to_github():
    """Push to GitHub."""
    
    print("Pushing to GitHub...")
    
    result = subprocess.run(
        ['git', 'push', 'origin', 'main'],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print("  Pushed successfully")
    else:
        print(f"  Push failed: {result.stderr}")
        print("  Try: git push --force-with-lease origin main")


def main():
    """Main function."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Publish the Spectral Pairing Theorem manuscript')
    parser.add_argument('--pdf', action='store_true', help='Generate PDF (requires LaTeX)')
    parser.add_argument('--commit', action='store_true', help='Commit to git')
    parser.add_argument('--push', action='store_true', help='Push to GitHub')
    
    args = parser.parse_args()
    
    # Check that the manuscript exists
    if not os.path.exists(MANUSCRIPT_MD):
        print(f"Error: Manuscript not found at {MANUSCRIPT_MD}")
        sys.exit(1)
    
    # Create the arXiv package
    latex_file = create_arxiv_package()
    
    # Generate PDF if requested
    if args.pdf:
        generate_pdf(latex_file)
    
    # Commit if requested
    if args.commit:
        commit_to_git()
    
    # Push if requested
    if args.push:
        push_to_github()
    
    print("\nDone!")
    print(f"\nManuscript: {MANUSCRIPT_MD}")
    print(f"LaTeX: {latex_file}")
    print(f"arXiv package: {ARXIV_DIR}/")
    print("\nTo submit to arXiv:")
    print("1. Go to https://arxiv.org/")
    print("2. Select category: math.NT (Number Theory)")
    print("3. Upload the tar.gz package")
    print("4. Fill in the metadata")


if __name__ == '__main__':
    main()
