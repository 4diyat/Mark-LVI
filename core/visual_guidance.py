"""Prompt guidance only for visual tools actually offered this session."""


def guidance(names):
    names = set(names)
    lines = []
    if 'present_content' in names:
        lines.append('For a visual explanation when useful or requested, present_content can show '
                     'concept or comparison cards, ordered steps, or a timeline; choose a form '
                     'that fits the information you are conveying. Do not invent facts, sources or dates.')
    if 'visualize_data' in names:
        lines.append('For numeric data actually supplied by the user or returned by a tool, '
                     'visualize_data can show a chart and table; do not invent values or attribution.')
    if lines:
        lines.append('Do not open content when the user declines it. Displayed material is not '
                     'automatically synchronized with speech; do not claim it is. Only say it opened '
                     'after the tool confirms success. Source attribution is not independently verified.')
    return '\n'.join(lines)
