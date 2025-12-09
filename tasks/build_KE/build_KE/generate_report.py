
def generate_report(result_dict: dict, topic: str) -> str:
    """
    Generate a comprehensive report based on the result_dict.
    
    Args:
        result_dict: Dictionary containing 'key_events', 'relationships', and 'evidence' lists
        topic: The topic name for context
    
    Returns:
        A formatted markdown report string
    """
    key_events = result_dict.get('key_events', [])
    relationships = result_dict.get('relationships', [])
    evidence = result_dict.get('evidence', [])
    
    # Build event lookup
    events_by_id = {event['id']: event for event in key_events}
    
    # Count evidences per key event
    evidence_by_relationship = {}
    for ev in evidence:
        rel_id = ev.get('relationship_id')
        if rel_id:
            evidence_by_relationship[rel_id] = evidence_by_relationship.get(rel_id, 0) + 1
    
    # Count evidences per key event (through relationships)
    evidence_count_by_event = {}
    for rel in relationships:
        source_id = rel.get('source_event_id')
        target_id = rel.get('target_event_id')
        rel_id = rel.get('relationship_id')
        ev_count = evidence_by_relationship.get(rel_id, 0)
        
        if source_id:
            evidence_count_by_event[source_id] = evidence_count_by_event.get(source_id, 0) + ev_count
        if target_id:
            evidence_count_by_event[target_id] = evidence_count_by_event.get(target_id, 0) + ev_count
    
    # Count events by type
    event_type_counts = {}
    event_type_counts['MIE'] = sum(1 for e in key_events if e.get('event_type') == 'MIE')
    event_type_counts['KE'] = sum(1 for e in key_events if e.get('event_type') == 'KE')
    event_type_counts['AO'] = sum(1 for e in key_events if e.get('event_type') == 'AO')
    
    # Count events by biological level
    level_counts = {}
    for event in key_events:
        level = event.get('biological_level', 'unknown')
        level_counts[level] = level_counts.get(level, 0) + 1
    
    # Build relationship graph to find pathways
    # Create adjacency list: event_id -> list of (target_id, relationship)
    graph = {}
    for rel in relationships:
        source_id = rel.get('source_event_id')
        target_id = rel.get('target_event_id')
        if source_id and target_id:
            if source_id not in graph:
                graph[source_id] = []
            graph[source_id].append((target_id, rel))
    
    # Find an example AOP pathway (MIE -> KE -> ... -> AO)
    def find_pathway(start_id, visited=None):
        """Find a pathway from start_id to an AO"""
        if visited is None:
            visited = set()
        if start_id in visited:
            return None
        visited.add(start_id)
        
        event = events_by_id.get(start_id)
        if not event:
            return None
        
        # If we found an AO, return it
        if event.get('event_type') == 'AO':
            return [start_id]
        
        # Otherwise, explore neighbors
        if start_id in graph:
            for target_id, rel in graph[start_id]:
                path = find_pathway(target_id, visited.copy())
                if path:
                    return [start_id] + path
        
        return None
    
    # Find MIE events and try to build pathways
    example_pathway = None
    for event in key_events:
        if event.get('event_type') == 'MIE':
            pathway = find_pathway(event['id'])
            if pathway:
                example_pathway = pathway
                break
    
    # If no complete pathway found, just show the first few relationships
    if not example_pathway and relationships:
        # Build a simple path from first relationship
        first_rel = relationships[0]
        example_pathway = []
        if first_rel.get('source_event_id'):
            example_pathway.append(first_rel['source_event_id'])
        if first_rel.get('target_event_id'):
            example_pathway.append(first_rel['target_event_id'])
    
    # Get paper metadata
    paper_title = result_dict.get('title', 'Unknown Title')
    paper_summary = result_dict.get('summary', 'Summary not available')
    
    # Generate report
    report_lines = [
        f"# Key Event Extraction Report",
        "",
        "## Paper Information",
        "",
        f"**Title:** {paper_title}",
        "",
        f"**Topic of Interest:** {topic}",
        "",
        f"**Summary:** {paper_summary}",
        "",
        "## AOP Pathway Statistics",
        "",
        f"- **Total Key Events**: {len(key_events)}",
        f"  - MIE (Molecular Initiating Events): {event_type_counts.get('MIE', 0)}",
        f"  - KE (Key Events): {event_type_counts.get('KE', 0)}",
        f"  - AO (Adverse Outcomes): {event_type_counts.get('AO', 0)}",
        "",
        f"- **Total Relationships**: {len(relationships)}",
        "",
        f"- **Total Evidence Records**: {len(evidence)}",
        "",
        "## Events by Biological Level",
        ""
    ]
    
    # Add level breakdown
    for level, count in sorted(level_counts.items()):
        report_lines.append(f"- **{level.capitalize()}**: {count}")
    
    report_lines.extend([
        "",
        "## Evidence Count per Key Event",
        ""
    ])
    
    # Show top events by evidence count
    sorted_events = sorted(
        [(eid, count) for eid, count in evidence_count_by_event.items()],
        key=lambda x: x[1],
        reverse=True
    )
    
    if sorted_events:
        for eid, count in sorted_events[:10]:  # Show top 10
            event = events_by_id.get(eid)
            if event:
                event_name = event.get('name', 'Unknown')
                report_lines.append(f"- **{event_name}**: {count} evidence record(s)")
    else:
        report_lines.append("- No evidence records found")
    
    # Add example pathway
    report_lines.extend([
        "",
        "## Example AOP Pathway",
        ""
    ])
    
    if example_pathway:
        report_lines.append("The following is an example pathway extracted from the document:")
        report_lines.append("")
        for i, event_id in enumerate(example_pathway):
            event = events_by_id.get(event_id)
            if event:
                event_name = event.get('name', 'Unknown')
                event_type = event.get('event_type', '')
                bio_level = event.get('biological_level', '')
                arrow = " → " if i < len(example_pathway) - 1 else ""
                report_lines.append(f"{i+1}. **{event_name}** [{event_type}] ({bio_level}){arrow}")
        
        # Add relationship details for the pathway
        report_lines.append("")
        report_lines.append("**Pathway Details:**")
        for i in range(len(example_pathway) - 1):
            source_id = example_pathway[i]
            target_id = example_pathway[i + 1]
            
            # Find relationship
            rel = None
            for r in relationships:
                if (r.get('source_event_id') == source_id and 
                    r.get('target_event_id') == target_id):
                    rel = r
                    break
            
            if rel:
                strength = rel.get('evidence_strength', 0)
                justification = rel.get('evidence_justification', '')
                report_lines.append(f"- Step {i+1} → {i+2}: Evidence strength = {strength:.2f}")
                if justification:
                    report_lines.append(f"  *{justification[:200]}...*" if len(justification) > 200 else f"  *{justification}*")
    else:
        report_lines.append("No complete pathway found in the extracted data.")
    
    return "\n".join(report_lines) 