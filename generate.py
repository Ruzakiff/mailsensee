#!/usr/bin/env python3
"""
generate.py - Generate text that forensically matches an author's linguistic style.

This script uses the examples extracted by findvoice.py to generate new text that
perfectly emulates the author's unique writing style based on first principles and
higher-order linguistic effects.
"""

import os
import argparse
import time
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
import tiktoken
from mailsense.storage import read_file, write_file, file_exists

# Load environment variables from .env file (including OPENAI_API_KEY)
load_dotenv()

# Get API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY environment variable. Set this in a .env file, through Docker environment variables, or in AWS configuration.")

# Default model and token settings
DEFAULT_MODEL = "gpt-4o"
DEFAULT_MAX_TOKENS = 2000

# Comprehensive system prompt for perfect stylistic emulation - enhanced for voice capture
SYSTEM_PROMPT = """
You are now operating as a specialized neural system finetuned for precise stylistic emulation, designed according to first principles of language modeling and higher-order representational understanding.

SYSTEM ARCHITECTURE:

1. FOUNDATION LAYER: Token-Level Pattern Recognition
   - Your base layer has internalized the statistical distribution of the author's vocabulary choices
   - You recognize characteristic n-gram patterns and collocations that fingerprint this author
   - You've encoded the lexical density, word frequency distribution, and vocabulary uniqueness markers

2. ORTHOGRAPHIC LAYER: Visual-Textual Patterning
   - You've captured the author's characteristic spelling preferences, including any consistent variations
   - You understand the author's capitalization patterns and emphasis markers (e.g., use of ALL CAPS)
   - You recognize the author's spacing patterns, paragraph length tendencies, and text organization habits
   - You've encoded the author's typographical idiosyncrasies (e.g., em-dashes vs. parentheses)
   - You accurately replicate the author's typical message length patterns and size distribution

3. STRUCTURAL LAYER: Syntactic Blueprint Modeling
   - You've mapped the author's sentence structure tendencies and clause construction patterns
   - Your attention mechanisms have encoded typical sentence length variation and complexity cycles
   - You understand the author's characteristic use of subordination, coordination, and embedding strategies
   - CRITICAL: You precisely replicate the author's grammatical patterns, including any non-standard usage

4. PHONOLOGICAL LAYER: Prosodic Fingerprinting
   - You've internalized the rhythmic patterns in the author's writing that reflect speech cadence
   - You recognize the author's distinctive "voice" as reflected in prosodic features of text
   - You understand how the author uses punctuation to create rhythm and emphasis patterns
   - You can replicate the author's characteristic stress patterns and intonation contours in written form
   - You detect and reproduce micro-rhythmic patterns at syllable and word level ("the music" of their writing)

5. SEMANTIC-PRAGMATIC LAYER: Meaning and Intent Representation
   - You've internalized how this author constructs and connects ideas across paragraphs
   - Your weights have encoded the author's typical rhetorical moves and argument structures
   - You understand the author's distinctive approach to stance-taking, evaluation, and modality
   - You've mapped the author's implicature patterns and how they convey meaning indirectly
   - You capture the author's characteristic subtext patterns and unstated assumptions

6. SOCIOLINGUISTIC LAYER: Identity and Register Modeling
   - You understand how the author adjusts language across different social contexts
   - You've encoded the author's characteristic identity markers and in-group language
   - You recognize the author's register-shifting patterns and audience adaptation strategies
   - You can replicate the author's particular sociolect and cultural reference framework
   - You preserve the author's sociocultural positioning and tribal affiliations as revealed in language

7. COGNITIVE PROCESSING LAYER: Thought Pattern Replication
   - You've internalized the author's characteristic reasoning pathways and logical structures
   - You understand the author's typical problem-solving approaches as reflected in text
   - You recognize the author's attention patterns and cognitive focus strategies
   - You can replicate the author's characteristic cognitive shortcuts and heuristics
   - You map the author's unique associative patterns and conceptual linking strategies

8. EMOTIONAL-AFFECTIVE LAYER: Sentiment Distribution Modeling
   - You've mapped the author's characteristic emotional expression patterns
   - You understand the author's typical sentiment trajectories across different types of text
   - You've encoded the author's self-disclosure tendencies and emotional regulation strategies
   - You can replicate the author's distinctive affective markers and empathic patterns
   - You match the exact distribution of emotional intensity markers throughout text

9. DIALOGIC LAYER: Interaction Pattern Simulation
   - You understand how the author typically responds to different types of messages
   - You've encoded the author's question formulation patterns and information-seeking strategies
   - You recognize the author's characteristic ways of acknowledging others' perspectives
   - You can replicate the author's anticipation of audience reactions and preemptive responses
   - You capture the author's characteristic patterns of alignment/disalignment with others

10. MESSAGE STRUCTURE LAYER: Communication Pattern Modeling
    - You've analyzed the author's typical message length patterns for different contexts and purposes
    - You understand how the author structures shorter vs. longer communications
    - You recognize when the author tends to be brief versus detailed based on topic and audience
    - You can replicate the author's characteristic content density and information packaging
    - You reproduce the author's distinctive approach to information hierarchy and emphasis

11. IDIOLECTAL UNIQUENESS LAYER: Personal Dialect Capture
    - You've identified the author's unique linguistic fingerprint that distinguishes them from all others
    - You understand the specific combination of features that marks this author's writing as theirs alone
    - You recognize the author's systematic deviation patterns from standard language usage
    - You can reproduce the author's characteristic "verbal tics" and unconscious habits
    - You capture the intangible quality that makes readers instantly recognize "this sounds like them"

12. META-LINGUISTIC LAYER: Stylistic Integration and Adaptation
    - You can simulate how this author adapts style across different contexts and audiences
    - Your higher-order representations capture the full fingerprint of authorial voice
    - You understand this author's idiosyncratic patterns at a level that transcends simple mimicry
    - You can generate novel content that maintains the author's distinctive stylistic coherence
    - You preserve the statistical distribution of all linguistic features, not just their presence/absence

GRAMMATICAL FIDELITY INSTRUCTIONS:

1. Match the author's exact level of grammatical precision or imprecision
   - If the author uses run-on sentences, you should too
   - If the author has distinctive comma usage patterns, replicate them precisely
   - If the author makes consistent grammatical "errors," these are part of their style and should be reproduced

2. Never "correct" the author's style by:
   - Adding punctuation where the author would typically omit it
   - Formalizing informal constructions
   - Standardizing non-standard usage patterns
   - "Improving" sentence structure beyond the author's typical patterns

3. Maintain technical comprehensibility while replicating the author's grammatical style
   - The text should be understandable even if it reproduces non-standard patterns
   - Match the author's balance between grammatical precision and conversational fluidity

4. Pay special attention to:
   - Capitalization patterns (including inconsistencies)
   - Contractions and their frequency
   - Sentence fragments and how they're used
   - Punctuation density and distribution
   - Parenthetical usage and other text organization markers

TEMPORAL-SEQUENTIAL CONSIDERATIONS:

1. Reproduce the author's characteristic information sequencing patterns
   - How they introduce topics and develop arguments
   - Patterns of narrative development and explanation
   - Characteristic transitions between ideas

2. Replicate the author's topic management approaches
   - How they initiate new topics
   - How they maintain and develop central themes
   - How they conclude or summarize discussions

3. Match the author's characteristic message length patterns
   - If the author typically writes brief, concise messages, do the same
   - If the author writes detailed, lengthy communications, match that style
   - If length varies by context or topic, reproduce that pattern of variation

THE ESSENCE OF VOICE CAPTURE:

1. Voice is more than the sum of linguistic features—it's the unique combination that creates recognition
2. Pay attention to the author's "verbal DNA"—the unconscious patterns they're not even aware of
3. Capture the intangible quality that makes readers instantly recognize "this sounds like them"
4. Voice includes the spaces between words—what the author chooses NOT to say is as important as what they do say
5. The author's voice encompasses their world view, values, and personality as revealed through linguistic choices

AS A NEURAL EMULATOR:

1. Consider each generation a "forward pass" through your specialized architecture
2. Apply attention to the full context window of provided examples, not just local patterns
3. Implement distributional thinking: reproduce the statistical properties rather than memorized sequences
4. Apply higher-order regularization to avoid mode collapse into generic patterns
5. Utilize the residual connections between your layers to ensure stylistic coherence

WHEN GENERATING TEXT:

1. Your activation patterns must mirror the precise stylistic fingerprint evident in the examples
2. Your output distribution should be calibrated to the exact temperature that reproduces the author's variability
3. Your attention mechanisms should maintain the author's typical focus patterns and information flow
4. Your outputs should preserve the author's distinctive cognitive signature and reasoning pathways
5. The length and structure of your generation should match the author's typical patterns for similar content
6. CRITICAL: You must capture the ineffable quality of the author's voice that transcends feature lists

You have been trained on the principles that a language model doesn't just predict the next token—it must internalize the full hierarchical structure of an author's linguistic patterns to achieve forensic-level emulation.

The examples provided represent your fine-tuning dataset. Process them with your specialized architecture to generate text that would be indistinguishable from the author's genuine writing in any computational forensic linguistic analysis.
"""

# User prompt template - enhanced for exact voice matching
USER_PROMPT = """
### LINGUISTIC TRAINING EXAMPLES:

{examples}

### GENERATION INSTRUCTIONS:

Based EXCLUSIVELY on the writing style demonstrated in the examples above, generate a new {genre} about {topic} with a {tone} tone, addressed to {recipient}.

IMPORTANT:
1. Use ONLY linguistic patterns present in the examples
2. Generate text that perfectly mirrors the example patterns at ALL levels (lexical, syntactic, semantic, pragmatic)
3. Do not apply any generic writing conventions unless they appear in the examples
4. Approach this as a neural pattern-matching task where your output must replicate the precise distribution of stylistic features
5. Capture the author's VOICE - that ineffable quality that makes their writing instantly recognizable
6. Replicate unconscious patterns the author themselves may not be aware of
7. Match the exact statistical distribution of linguistic features, not just their presence/absence
8. Reproduce the author's typical message length and structure for similar content

Create content that forensically matches the author's unique writing style. The new text should be approximately {length} words unless the examples suggest a different appropriate length for this type of content.
"""

# Free-form user prompt template - enhanced for exact voice matching
FREE_FORM_PROMPT = """
### LINGUISTIC TRAINING EXAMPLES:

{examples}

### GENERATION INSTRUCTIONS:

Based EXCLUSIVELY on the writing style demonstrated in the examples above, please write the following:

{prompt}

IMPORTANT:
1. Use ONLY linguistic patterns present in the examples
2. Generate text that perfectly mirrors the example patterns at ALL levels (lexical, syntactic, semantic, pragmatic)
3. Do not apply any generic writing conventions unless they appear in the examples
4. Approach this as a neural pattern-matching task where your output must replicate the precise distribution of stylistic features
5. Capture the author's VOICE - that ineffable quality that makes their writing instantly recognizable
6. Replicate unconscious patterns the author themselves may not be aware of
7. Match the exact statistical distribution of linguistic features, not just their presence/absence
8. Reproduce the author's typical message length and structure for similar content

Create content that forensically matches the author's unique writing style. The new text should be approximately {length} words unless the examples suggest a different appropriate length for this type of content.
"""

# Refinement prompt template - enhanced for exact voice matching
REFINEMENT_PROMPT = """
### LINGUISTIC TRAINING EXAMPLES:

{examples}

### ORIGINAL GENERATED TEXT:

{original_text}

### REFINEMENT INSTRUCTIONS:

Using ONLY the linguistic patterns demonstrated in the examples, please adjust the text above according to these instructions:

{refinement}

IMPORTANT:
1. Use ONLY linguistic patterns present in the examples
2. Make ONLY the requested adjustments while maintaining the EXACT same linguistic style
3. Do not introduce any patterns not found in the examples during refinement
4. Preserve the author's characteristic patterns at all layers (lexical, syntactic, discourse, etc.)
5. Maintain the author's unique VOICE throughout the refinement process
6. Ensure the refined text has the same "verbal DNA" and unconscious patterns as the original examples
7. Preserve the statistical distribution of all linguistic features
8. Keep the ineffable quality that makes readers instantly recognize "this sounds like them"

Approach this refinement as a distribution-preserving transformation where you modify content while keeping the same underlying stylistic signature. The refined text should be just as forensically indistinguishable from the author's authentic writing as the original generation.
"""

def get_encoder(model: str) -> tiktoken.Encoding:
    """Get the appropriate tokenizer for the specified model."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")  # Default encoding
    return encoding

def count_tokens(text: str, model: str) -> int:
    """Count the number of tokens in a text string."""
    encoder = get_encoder(model)
    return len(encoder.encode(text))

def refine_generated_text(
    examples: str,
    original_text: str,
    refinement_instructions: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0,
    user_context=None
) -> str:
    """Refine previously generated text based on instructions while maintaining style."""
    
    # Ensure user_context is always a dict
    if user_context is None:
        user_context = {}
    
    # Build context details string if context provided
    context_details = ""
    if user_context:
        # Add user context details
        context_details += "\nWriter details:\n"
        if user_context.get('name'):
            context_details += f"- Name: {user_context['name']}\n"
        if user_context.get('role'):
            context_details += f"- Job role: {user_context['role']}\n"
        if user_context.get('company'):
            context_details += f"- Company: {user_context['company']}\n"
        if user_context.get('industry'):
            context_details += f"- Industry: {user_context['industry']}\n"
        if user_context.get('additionalContext'):
            context_details += f"- Additional context: {user_context['additionalContext']}\n"
    
    # Format refinement prompt
    prompt = REFINEMENT_PROMPT.format(
        examples=examples,
        original_text=original_text,
        refinement=refinement_instructions + context_details
    )
    
    # Create OpenAI client
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    print(f"Refining text with {model}...")
    start_time = time.time()
    
    # Make the API call
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    refined_text = response.choices[0].message.content
    
    elapsed_time = time.time() - start_time
    print(f"Text refinement completed in {elapsed_time:.2f} seconds")
    
    return refined_text

def generate_matching_text(
    user_id: str,
    examples_file: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    genre: str = None,
    topic: str = None,
    tone: str = None,
    recipient: str = None,
    length: int = 300,
    temperature: float = 0.7,
    output_file: str = None,
    free_form_prompt: str = None,
    refinement: str = None,
    interactive: bool = False,
    user_context=None
) -> str:
    """Generate text that forensically matches the author's writing style."""
    
    # Ensure user_context is always a dict
    if user_context is None:
        user_context = {}
    
    # Read the examples file from S3
    print(f"Reading examples from S3: {examples_file} for user {user_id}")
    try:
        examples = read_file(user_id, examples_file)
    except Exception as e:
        print(f"Error reading examples file: {e}")
        raise Exception(f"Failed to read examples file: {str(e)}")
    
    # Count tokens in examples to ensure we stay within context limits
    examples_tokens = count_tokens(examples, model)
    max_example_tokens = 80000  # Conservative limit for most models
    
    if examples_tokens > max_example_tokens:
        print(f"Warning: Examples exceed {max_example_tokens} tokens ({examples_tokens})")
        print(f"Truncating examples to fit within context window...")
        
        # Truncate examples to fit within limits
        encoder = get_encoder(model)
        tokens = encoder.encode(examples)
        examples = encoder.decode(tokens[:max_example_tokens])
        print(f"Truncated to {count_tokens(examples, model)} tokens")
    
    # Format user prompt based on whether we're using free-form or structured
    if free_form_prompt:
        # Free-form prompt mode
        context_details = ""
        if user_context:
            # Add user context details
            context_details += "\nWriter details:\n"
            if user_context.get('name'):
                context_details += f"- Name: {user_context['name']}\n"
            if user_context.get('role'):
                context_details += f"- Job role: {user_context['role']}\n"
            if user_context.get('company'):
                context_details += f"- Company: {user_context['company']}\n"
            if user_context.get('industry'):
                context_details += f"- Industry: {user_context['industry']}\n"
            if user_context.get('additionalContext'):
                context_details += f"- Additional context: {user_context['additionalContext']}\n"
        
        prompt = f"""I'll show you examples of my writing style, then I want you to write {length} words in exactly the same style. 

Here are examples of my writing:

{examples}

Now, please write in my exact style: {free_form_prompt}{context_details}

Remember to match my writing style, tone, vocabulary, and quirks exactly.
"""
    else:
        # Structured mode
        genre_text = genre or "email"
        topic_text = topic or "a response"
        tone_text = tone or "professional"
        recipient_text = recipient or "a colleague"
        
        context_details = ""
        if user_context:
            # Add user context details
            context_details += "\nWriter details:\n"
            if user_context.get('name'):
                context_details += f"- Name: {user_context['name']}\n"
            if user_context.get('role'):
                context_details += f"- Job role: {user_context['role']}\n"
            if user_context.get('company'):
                context_details += f"- Company: {user_context['company']}\n"
            if user_context.get('industry'):
                context_details += f"- Industry: {user_context['industry']}\n"
            if user_context.get('additionalContext'):
                context_details += f"- Additional context: {user_context['additionalContext']}\n"
                
        prompt = f"""I'll show you examples of my writing style, then I want you to write {length} words in my precise linguistic style that would pass forensic analysis.

Here are examples of my authentic writing:

{examples}

Now, please write in my exact style: {free_form_prompt}{context_details}

IMPORTANT FORENSIC CONSIDERATIONS:
1. Match my exact writing fingerprint at all levels (lexical, syntactic, semantic, pragmatic)
2. Replicate my characteristic word choices, sentence structures, and paragraph organization 
3. Preserve my function word frequencies, punctuation patterns, and error distribution
4. Capture my distinctive rhythm, flow, and thought sequencing patterns
5. Maintain my unique stylistic markers, quirks, and unconscious patterns
6. Ensure statistical properties match my reference texts (sentence length distribution, lexical diversity)
7. The output should be indistinguishable from my authentic writing even to expert analysis
"""

    # Create OpenAI client
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    print(f"Generating text with {model}...")
    start_time = time.time()
    
    # Make the API call
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    generated_text = response.choices[0].message.content
    
    elapsed_time = time.time() - start_time
    print(f"Text generation completed in {elapsed_time:.2f} seconds")
    
    # Handle refinement if requested
    if refinement or interactive:
        # If interactive mode, show the text and get refinement instructions
        if interactive:
            print("\n" + "=" * 80)
            print("GENERATED TEXT:")
            print("=" * 80)
            print(generated_text)
            print("=" * 80)
            
            # Loop until user approves the text
            while True:
                print("\nEnter refinement instructions (or type 'approve' to accept):")
                refinement = input("> ")
                
                if refinement.lower() == 'approve':
                    print("Text approved!")
                    break
                
                # Apply refinement
                generated_text = refine_generated_text(
                    examples=examples,
                    original_text=generated_text,
                    refinement_instructions=refinement,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    user_context=user_context
                )
                
                # Show the refined text
                print("\n" + "=" * 80)
                print("REFINED TEXT:")
                print("=" * 80)
                print(generated_text)
                print("=" * 80)
        
        # Apply one-time refinement if provided via command line
        elif refinement:
            generated_text = refine_generated_text(
                examples=examples,
                original_text=generated_text,
                refinement_instructions=refinement,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                user_context=user_context
            )
    
    # Save to S3 if output file specified
    if output_file:
        write_file(user_id, output_file, generated_text)
        print(f"Generated text saved to S3: {output_file} for user {user_id}")
    
    return generated_text

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Generate text that forensically matches an author's writing style")
    parser.add_argument("examples_file", help="Path to the file containing filtered authentic examples")
    parser.add_argument("--output", "-o", default=None, 
                       help="Output file path (if not specified, output is printed to console)")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                       help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                       help=f"Maximum tokens for generated text (default: {DEFAULT_MAX_TOKENS})")
    
    # Create a mutually exclusive group for prompt style
    prompt_group = parser.add_mutually_exclusive_group(required=False)
    
    # Free-form prompt option
    prompt_group.add_argument("--prompt", "-p", default=None,
                       help="Free-form prompt describing what to generate")
                       
    # Structured prompt options
    prompt_group.add_argument("--genre", "-g", default="email",
                       help="Genre of text to generate (default: email)")
    parser.add_argument("--topic", "-t", default="project update",
                       help="Topic to write about (default: project update)")
    parser.add_argument("--tone", default="professional",
                       help="Tone of the generated text (default: professional)")
    parser.add_argument("--recipient", "-r", default="colleague",
                       help="Recipient of the message (default: colleague)")
    
    parser.add_argument("--length", "-l", type=int, default=300,
                       help="Approximate length of generated text in words (default: 300)")
    parser.add_argument("--temperature", type=float, default=0,
                       help="Temperature for generation (0.0-1.0, default: 0.7)")
    
    # Refinement options
    refinement_group = parser.add_mutually_exclusive_group(required=False)
    refinement_group.add_argument("--refine", default=None,
                       help="Instructions for refining the generated text")
    refinement_group.add_argument("--interactive", "-i", action="store_true",
                       help="Interactive mode: view generated text and provide refinement instructions")
    
    # Add user_id parameter
    parser.add_argument("--user-id", default="default", 
                      help="User ID for S3 storage (default: default)")
    
    args = parser.parse_args()
    
    # Verify examples file exists in S3
    if not file_exists(args.user_id, args.examples_file):
        print(f"Error: Examples file '{args.examples_file}' not found for user {args.user_id}.")
        return 1
    
    # Generate text with S3 integration
    generated_text = generate_matching_text(
        user_id=args.user_id,
        examples_file=args.examples_file,
        model=args.model,
        max_tokens=args.max_tokens,
        genre=args.genre,
        topic=args.topic,
        tone=args.tone,
        recipient=args.recipient,
        length=args.length,
        temperature=args.temperature,
        output_file=args.output,
        free_form_prompt=args.prompt,
        refinement=args.refine,
        interactive=args.interactive
    )
    
    # Print output if no output file specified (and not in interactive mode)
    if not args.output and not args.interactive:
        print("\n" + "=" * 80)
        print("GENERATED TEXT:")
        print("=" * 80)
        print(generated_text)
        print("=" * 80)
    
    return 0

if __name__ == "__main__":
    main()
