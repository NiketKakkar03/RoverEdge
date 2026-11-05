# Confirm scene geometry separately from visual target grounding

A photograph provides a rough scene draft whose scale, obstacle footprints, dock, and targets the user confirms in an editor; it does not establish automatically measured geometry. The confirmed scene supplies simulation geometry and traversability, while SAM grounds the requested target from a fresh rendered image after edits. This trades automatic reconstruction and live mapping for reproducible experiments, while preserving a real perception step instead of selecting targets through hidden simulator object IDs.
