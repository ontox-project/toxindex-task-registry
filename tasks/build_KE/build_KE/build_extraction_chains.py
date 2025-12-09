from build_KE.data_model import KeyEventsList, RelationshipsList, RelationshipStrength, PaperMetadata
from langchain_core.prompts import ChatPromptTemplate

def build_extraction_chains(llm):
    extract_events_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Extract CHEMICAL-AGNOSTIC key events from article related to {topic}.\n\n"
            
            "CRITICAL: Extract events AFTER metabolic transformation. Do NOT include:\n"
            "- Parent chemical exposure events\n"
            "- Metabolic transformation events\n"
            "Start from the biologically active form interacting with molecular targets.\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "CANONICAL NAMING - STRICT FORMAT\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "Use this EXACT format: '[Direction] of [Entity] in [Location]'\n\n"
            
            "Direction terms (choose ONE):\n"
            "- Increased/Decreased (for quantities, levels, rates)\n"
            "- Activation/Inhibition (for enzymes, receptors, pathways)\n"
            "- Enhanced/Reduced (for processes, activities)\n"
            "- Induction/Suppression (for gene expression, responses)\n"
            "- Disruption (for homeostasis, normal function)\n\n"
            
            "Entity (use official nomenclature):\n"
            "- Gene/protein symbols: AhR, NF-κB, CYP1A1, ER-α\n"
            "- Process names: oxidative stress, apoptosis, steroidogenesis\n"
            "- Anatomical terms: follicular cells, hepatocytes, dopaminergic neurons\n\n"
            
            "Location (when relevant):\n"
            "- 'in [cell type]': in hepatocytes, in neurons\n"
            "- 'in [tissue]': in liver tissue, in brain\n"
            "- 'in [organ]': in thyroid, in ovary\n"
            "- Omit if location is not specific or already implied\n\n"
            
            "CORRECT FORMAT EXAMPLES:\n"
            "✓ 'Activation of aryl hydrocarbon receptor'\n"
            "✓ 'Increased CYP1A1 expression in hepatocytes'\n"
            "✓ 'Inhibition of steroidogenesis in gonads'\n"
            "✓ 'Decreased glutathione levels in liver'\n"
            "✓ 'Disruption of thyroid hormone synthesis'\n"
            "✓ 'Apoptosis of dopaminergic neurons in substantia nigra'\n"
            "✓ 'Reduced insulin sensitivity in adipocytes'\n"
            "✓ 'Enhanced oxidative stress in mitochondria'\n\n"
            
            "INCORRECT FORMAT:\n"
            "✗ 'Hyperprolactinemia' → Use: 'Increased prolactin secretion from pituitary'\n"
            "✗ 'Hypothalamic changes' → Use: 'Altered neuropeptide expression in hypothalamus'\n"
            "✗ 'Effects on liver' → Use: 'Hepatocellular necrosis' or specific effect\n"
            "✗ 'Altered development' → Use: 'Delayed sexual maturation' or specific alteration\n"
            "✗ 'Receptor binding' → Use: 'Activation of estrogen receptor' (needs direction)\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "CANONICAL DESCRIPTIONS - CRITICAL\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "Descriptions must be GENERIC and CANONICAL - describe the PROCESS, not examples:\n\n"
            
            "CORRECT (canonical process description):\n"
            "✓ 'Inhibition of the enzyme that converts testosterone to estradiol'\n"
            "✓ 'Programmed cell death of hormone-producing cells'\n"
            "✓ 'Reduction in the number of mature oocytes released during ovulation'\n"
            "✓ 'Decrease in cellular response to insulin signaling'\n\n"
            
            "INCORRECT (example-specific or chemical-specific):\n"
            "✗ 'PCDDs resulted in ova trapped' (mentions specific chemical)\n"
            "✗ 'Observed at high doses in rats' (experimental detail, not process)\n"
            "✗ 'DES has been shown to perturb' (chemical-specific)\n"
            "✗ 'Dose-dependent increase' (experimental observation, not process)\n\n"
            
            "Description guidelines:\n"
            "- Describe the biological mechanism or consequence\n"
            "- NEVER mention specific chemicals, doses, species, or experimental conditions\n"
            "- Use present tense, third person\n"
            "- Keep it brief (1-2 sentences max)\n"
            "- Omit description if the name is self-explanatory\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "BIOLOGICAL LEVEL ASSIGNMENT - WITH RELATIONSHIP AWARENESS\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "Remember: relationships can ONLY go from one level to SAME or HIGHER level.\n"
            "This means your level assignments must create a valid progression path.\n\n"
            
            "MOLECULAR level - Individual molecules, genes, proteins:\n"
            "✓ 'Activation of estrogen receptor'\n"
            "✓ 'Inhibition of aromatase enzyme'\n"
            "✓ 'Increased CYP1A1 gene expression'\n"
            "✓ 'DNA adduct formation'\n"
            "✓ 'Altered histone acetylation'\n"
            "✓ 'Decreased hormone levels in blood' (circulating molecules)\n\n"
            
            "CELLULAR level - Processes within or affecting whole cells:\n"
            "✓ 'Increased cell proliferation'\n"
            "✓ 'Apoptosis of hepatocytes'\n"
            "✓ 'Oxidative stress in cells'\n"
            "✓ 'Disruption of calcium homeostasis'\n"
            "✓ 'Cell cycle arrest'\n"
            "✓ 'Reduced insulin sensitivity' (cellular response)\n\n"
            
            "TISSUE level - Effects on organized cell populations:\n"
            "✓ 'Hepatic necrosis'\n"
            "✓ 'Uterine hyperplasia'\n"
            "✓ 'Increased follicular cell height in thyroid tissue'\n"
            "✓ 'Fibrosis in liver tissue'\n"
            "✓ 'Epithelial hypertrophy'\n"
            "✓ 'Follicular atresia in ovary'\n\n"
            
            "ORGAN level - Dysfunction or structural changes of entire organs:\n"
            "✓ 'Decreased ovarian weight'\n"
            "✓ 'Thyroid gland enlargement'\n"
            "✓ 'Altered hormone secretion from pituitary' (organ function)\n"
            "✓ 'Hepatomegaly' (liver enlargement)\n"
            "✓ 'Renal dysfunction'\n"
            "✓ 'Testicular atrophy'\n\n"
            
            "ORGANISM level - Whole-body systemic effects, behavior, disease states:\n"
            "✓ 'Decreased body weight'\n"
            "✓ 'Altered mating behavior'\n"
            "✓ 'Impaired locomotor activity'\n"
            "✓ 'Delayed sexual maturation'\n"
            "✓ 'Reduced fertility' (reproductive capacity of individual)\n"
            "✓ 'Diabetes mellitus' (systemic disease)\n"
            "✓ 'Increased tumor incidence' (disease outcome)\n\n"
            
            "POPULATION level - Effects on groups:\n"
            "✓ 'Population decline'\n"
            "✓ 'Altered sex ratio in population'\n"
            "✓ 'Reduced reproductive success in population'\n\n"
            
            "CRITICAL DISTINCTIONS:\n"
            "- Hormone SECRETION = organ level (organ function)\n"
            "- Hormone LEVELS in blood = molecular level (circulating molecules)\n"
            "- Cellular RESPONSE to hormone = cellular level\n"
            "- BEHAVIOR change = organism level\n"
            "- DISEASE state = organism level\n"
            "- Organ FUNCTION change = organ level\n"
            "- Organ STRUCTURE change = organ level\n\n"
            
            "Think: Can this event lead to events at higher levels?\n"
            "If yes, assign it to a level that allows valid progression.\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "EVENT TYPE ASSIGNMENT\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "MIE (Molecular Initiating Event):\n"
            "- ALWAYS at molecular level\n"
            "- First molecular interaction\n"
            "- Examples: 'Activation of aryl hydrocarbon receptor', 'Inhibition of acetylcholinesterase'\n"
            "- Exactly ONE per pathway\n\n"
            
            "KE (Key Event):\n"
            "- Can be at ANY level (molecular through organism)\n"
            "- Intermediate measurable changes\n"
            "- Must be connected via valid level progression\n"
            "- Multiple KEs form the pathway\n\n"
            
            "AO (Adverse Outcome):\n"
            "- Usually organism or population level\n"
            "- Final harmful outcome\n"
            "- Examples: 'Reproductive failure', 'Neurodevelopmental disorders', 'Population decline'\n"
            "- Exactly ONE per pathway\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "CHEMICAL-AGNOSTIC REQUIREMENT\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "NEVER mention specific chemicals in names OR descriptions:\n"
            "✗ 'BPA-induced receptor activation'\n"
            "✗ 'TCDD binds to AhR'\n"
            "✗ 'PCDDs resulted in...'\n"
            "✗ 'DES exposure effects'\n"
            "✗ 'Following treatment with compound X...'\n\n"
            
            "✓ 'Activation of aryl hydrocarbon receptor'\n"
            "✓ 'Inhibition of steroidogenesis'\n"
            "✓ 'Disruption of thyroid hormone synthesis'\n"
            "✓ 'Programmed cell death in target tissue'\n\n"
            
            "Output JSON only. No explanatory text."
        )),
        ("human", "Article:\n{doc_text}\n\nExtract chemical-agnostic key events for {topic}.")
    ])
    
    extract_relationships_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Identify 'leads_to' relationships between key events.\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "BIOLOGICAL LEVEL PROGRESSION RULES - MANDATORY\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "Relationships can ONLY go from one level to SAME or HIGHER level:\n\n"
            
            "Level hierarchy (0 = lowest, 5 = highest):\n"
            "0. molecular\n"
            "1. cellular\n"
            "2. tissue\n"
            "3. organ\n"
            "4. organism\n"
            "5. population\n\n"
            
            "Valid transitions (→ means 'leads_to'):\n"
            "molecular (0) → molecular, cellular, tissue, organ, organism, population\n"
            "cellular (1) → cellular, tissue, organ, organism, population\n"
            "tissue (2) → tissue, organ, organism, population\n"
            "organ (3) → organ, organism, population\n"
            "organism (4) → organism, population\n"
            "population (5) → population\n\n"
            
            "FORBIDDEN transitions (backward progression):\n"
            "✗ cellular → molecular\n"
            "✗ tissue → molecular or cellular\n"
            "✗ organ → molecular, cellular, or tissue\n"
            "✗ organism → any lower level\n"
            "✗ population → any lower level\n\n"
            
            "PREFER GRADUAL progression when intermediate events exist:\n"
            "✓ BEST: molecular → cellular → tissue → organ → organism\n"
            "⚠ ACCEPTABLE: molecular → tissue → organism (if no cellular event described)\n"
            "✗ AVOID: molecular → organism (only if absolutely no intermediates)\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "CORRECT PROGRESSION EXAMPLES\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "Example pathway 1:\n"
            "✓ 'Activation of AhR' (molecular)\n"
            "  → 'Increased CYP1A1 expression' (molecular)\n"
            "  → 'Enhanced oxidative stress' (cellular)\n"
            "  → 'Apoptosis of hepatocytes' (cellular)\n"
            "  → 'Hepatic necrosis' (tissue)\n"
            "  → 'Liver failure' (organ)\n"
            "  → 'Mortality' (organism)\n\n"
            
            "Example pathway 2:\n"
            "✓ 'Inhibition of aromatase' (molecular)\n"
            "  → 'Decreased estrogen synthesis' (molecular)\n"
            "  → 'Altered follicular development' (tissue)\n"
            "  → 'Impaired ovulation' (organ)\n"
            "  → 'Reduced fertility' (organism)\n\n"
            
            "Example pathway 3:\n"
            "✓ 'Activation of estrogen receptor' (molecular)\n"
            "  → 'Increased cell proliferation' (cellular)\n"
            "  → 'Uterine hyperplasia' (tissue)\n"
            "  → 'Endometrial cancer' (organism)\n\n"
            
            "═══════════════════════════════════════════════════════════════\n"
            "INSTRUCTIONS\n"
            "═══════════════════════════════════════════════════════════════\n"
            
            "1. Review all extracted events and their biological levels\n"
            "2. Create causal pathway from MIE → intermediate KEs → AO\n"
            "3. Ensure EVERY relationship follows level progression rules\n"
            "4. Prefer gradual progression through adjacent levels\n"
            "5. Only skip levels if no intermediate event exists\n\n"
            
            "Output JSON only. No explanatory text."
        )),
        ("human", "Article:\n{doc_text}\n\nEvents:\n{events_json}\n\nExtract relationships.")
    ])
    
    score_relationship_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Score evidence strength for the causal relationship (0-1).\n\n"
            "Scoring criteria:\n"
            "0.9-1.0: Strong causal evidence (dose-response, temporal sequence, mechanism explained, quantitative)\n"
            "0.6-0.8: Strong association (mechanistic plausibility, consistent observations)\n"
            "0.3-0.5: Suggestive evidence (correlation, limited mechanistic data)\n"
            "0.0-0.2: Weak/speculative (indirect connection, hypothetical)\n\n"
            "Consider:\n"
            "- Causal language strength ('causes' > 'associated with' > 'correlated with')\n"
            "- Dose-response relationship present\n"
            "- Temporal sequence established\n"
            "- Mechanistic explanation provided\n"
            "- Quantitative measurements\n"
            "- Study design quality\n"
            "- Replication across studies\n\n"
            "Output JSON only."
        )),
        ("human", "Article:\n{doc_text}\n\nUpstream:\n{source_event}\n\nDownstream:\n{target_event}")
    ])
    
    extract_metadata_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Extract the title and provide a brief summary of the research paper.\n\n"
            "For the title:\n"
            "- Extract the exact title from the document\n"
            "- If the title is not clearly visible, use the first major heading or the most prominent text\n\n"
            "For the summary:\n"
            "- Provide a concise 2-3 sentence summary of the paper's main focus and findings\n"
            "- Focus on the key research question, methodology (if relevant), and primary conclusions\n"
            "- Keep it brief and informative\n\n"
            "Output JSON only. No explanatory text."
        )),
        ("human", "Article:\n{doc_text}\n\nExtract the title and provide a brief summary.")
    ])
    
    return {
        'extract_events': extract_events_prompt | llm.with_structured_output(KeyEventsList),
        'extract_relationships': extract_relationships_prompt | llm.with_structured_output(RelationshipsList),
        'score_relationship': score_relationship_prompt | llm.with_structured_output(RelationshipStrength),
        'extract_metadata': extract_metadata_prompt | llm.with_structured_output(PaperMetadata)
    }