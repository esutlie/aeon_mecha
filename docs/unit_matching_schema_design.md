# Unit Matching Schema Design

## Overview

The unit matching schema enables tracking of spike-sorted units across multiple recording sessions (ephys blocks) from the same animal and probe. This allows researchers to identify the same biological neuron across different time periods, even when that neuron is assigned different unit IDs in different sorting sessions.

The schema supports incremental matching: as new ephys blocks are spike-sorted and curated, they can be matched against previously processed blocks to extend existing universal unit identities or create new ones.

## Purpose

In long-term electrophysiology experiments, recordings are typically broken into multiple ephys blocks (e.g., 30-hour blocks with 6-hour overlaps). Each block is spike-sorted independently, resulting in units that may represent the same biological neuron but have different unit IDs across sessions. 

The unit matching schema provides:
- **Universal Unit IDs**: Persistent identifiers for biological units across all recording sessions
- **Incremental Matching**: Ability to add new sessions to existing universal units as they become available
- **Multiple Algorithms**: Support for different matching methods (spike timing overlap, waveform correlation, etc.)
- **Audit Trail**: Tracking of when matching was executed and which sessions were processed

## Schema Location

All tables are part of the `spike_sorting` schema and should be defined in `aeon/dj_pipeline/spike_sorting.py`.

## Table Definitions

### UnitMatchingMethod (Lookup Table)

Defines the available unit matching algorithms/methods.

```python
@schema
class UnitMatchingMethod(dj.Lookup):
    definition = """
    # Method/algorithm for matching units across spike sorting sessions
    matching_method: varchar(32)
    ---
    matching_method_description: varchar(1000)
    """
    
    contents = [
        ("spike_time_overlap", "Matches units based on overlapping time windows and identical spike timing during overlap"),
        # Future: ("waveform_correlation", "Matches units based on waveform similarity and correlation"),
    ]
```

**Primary Key**: `matching_method` (varchar)

### UnitMatching (Computed Table)

Executes the unit matching algorithm for each new sorted session. This table tracks the execution of matching runs and ensures each session is only processed once per matching method.

```python
@schema
class UnitMatching(dj.Computed):
    definition = """
    # Runs unit matching algorithm for a new sorted session
    # Compares the new session against overlapping existing sessions and updates universal units
    # Only processes sessions that have been officially curated
    -> SortedSpikes
    -> UnitMatchingMethod
    ---
    execution_time: datetime  # datetime of when matching was executed
    execution_duration: float  # execution duration in hours
    """
    
    @property
    def key_source(self):
        """Only process SortedSpikes sessions that:
        1. Have been officially curated (ApplyOfficialCuration exists for this session)
        2. Have not yet been processed for this matching method
        """
        # Import the curation schema
        from aeon.dj_pipeline import spike_sorting_curation
        
        curated_sessions = SortedSpikes * UnitMatchingMethod * spike_sorting_curation.ApplyOfficialCuration
        already_matched = UnitMatching.proj()
        return curated_sessions - already_matched
```

**Primary Key**: All keys from `SortedSpikes` + `matching_method`

**Prerequisites**:
- Session must exist in `SortedSpikes`
- Session must have been officially curated (`spike_sorting_curation.ApplyOfficialCuration`)
- Session must not have already been processed for this matching method

**Implementation Notes**:
- The `make()` function should:
  1. Find all existing `SortedSpikes` sessions for the same subject+probe that have already been matched (exist in `UnitMatching`)
  2. Check for time overlap between the new session and existing sessions
  3. Run the matching algorithm pairwise between the new session and each overlapping existing session
  4. Create new universal units OR add to existing ones in `UniversalUnit`
  5. Insert matches into `UniversalUnit.UnitMatch`

### UniversalUnit (Manual Table)

Stores the universal unit identifiers that represent the same biological unit across sessions.

```python
@schema
class UniversalUnit(dj.Manual):
    definition = """
    # Universal unit IDs for tracking units across spike sorting sessions
    # Created and updated by unit matching algorithms to represent the same biological unit across sessions
    -> subject.Subject
    -> ephys.Probe
    -> UnitMatchingMethod
    universal_unit: int  # unique identifier for this universal unit within this subject+probe+method combination
    ---
    universal_unit_comment='': varchar(1000)  # optional comment about this universal unit
    """
    
    class UnitMatch(dj.Part):
        definition = """
        # Links per-session units (SortedSpikes.Unit) to universal units
        # Each row documents that a session unit belongs to this universal unit
        -> master
        -> SortedSpikes.Unit
        ---
        match_confidence=null: float  # optional confidence score from the matching algorithm
        match_comment='': varchar(1000)  # optional comment about the match
        """
```

**Primary Key**: `subject`, `probe`, `matching_method`, `universal_unit`

**Part Table (`UnitMatch`)**: Links session-specific units to universal units
- Primary Key: All keys from `UniversalUnit` + all keys from `SortedSpikes.Unit`
- Each row represents one session unit matched to one universal unit

**Implementation Notes**:
- This table is populated by `UnitMatching.make()`
- Multiple session units can belong to the same universal unit (representing the same biological neuron across sessions)
- Each session unit can only belong to one universal unit (enforced by DataJoint primary key constraints)

## Workflow

### Initial Setup

1. A new `UnitMatchingMethod` is added to define a matching algorithm
2. The algorithm implementation is added to `UnitMatching.make()`

### Matching Process (Incremental)

The matching process follows this workflow for each new curated session:

1. **Trigger**: When a new `SortedSpikes` session is curated (appears in `spike_sorting_curation.ApplyOfficialCuration`), `UnitMatching` becomes ready to process it

2. **Query Existing Sessions**: The `make()` function queries for:
   - All `SortedSpikes` sessions for the same `subject` + `probe` combination
   - Sessions that have already been processed (exist in `UnitMatching` for this `matching_method`)
   - Sessions that overlap in time with the new session

3. **Pairwise Matching**: For each overlapping existing session:
   - Run the matching algorithm (e.g., `spike_time_overlap`)
   - Identify which units from the new session match units from the existing session
   - Determine which existing universal units these matches belong to (or create new ones)

4. **Update Universal Units**: 
   - If a match is found with an existing universal unit: Add the new session unit to that universal unit via `UniversalUnit.UnitMatch`
   - If no match is found: Create a new universal unit and add the new session unit to it

5. **Logging**: Insert a row into `UnitMatching` to record:
   - Execution time
   - Execution duration
   - Which session was processed

### Example Scenario

Consider a 7-day experiment with overlapping 30-hour blocks:

**Day 1-2**: Block 1 is sorted and curated
- `UnitMatching` processes Block 1
- Creates Universal Unit 33 with Block 1, Unit 5

**Day 2-3**: Block 2 is sorted and curated (overlaps with Block 1)
- `UnitMatching` processes Block 2
- Compares Block 2 with Block 1
- Finds Block 2, Unit 8 matches Block 1, Unit 5
- Adds Block 2, Unit 8 to Universal Unit 33

**Day 3-4**: Block 3 is sorted and curated (overlaps with Block 2)
- `UnitMatching` processes Block 3
- Compares Block 3 with Block 2 (and potentially Block 1 if overlapping)
- Finds Block 3, Unit 11 matches Block 2, Unit 8
- Adds Block 3, Unit 11 to Universal Unit 33

**Result**: Universal Unit 33 contains:
- Block 1, Unit 5
- Block 2, Unit 8  
- Block 3, Unit 11

All three session units represent the same biological neuron across the different recording blocks.

## Key Design Decisions

### 1. Why Manual Table for UniversalUnit?

`UniversalUnit` is a Manual table (not Computed or Imported) because:
- It's populated by the matching algorithm logic in `UnitMatching.make()`
- Units persist and are incrementally updated as new sessions are added
- Manual tables allow flexible insert/update operations that Computed tables don't support

### 2. Why Computed Table for UnitMatching?

`UnitMatching` is a Computed table because:
- It automatically processes new sessions as they become available (after curation)
- The `key_source` property ensures proper prerequisites (curation, no duplicate processing)
- Execution logging is important for auditability

### 3. Incremental Matching Design

The schema supports incremental matching by:
- Each session is processed once when it becomes available
- Existing universal units are queried and extended with new matches
- No need to re-process all sessions when a new one arrives

### 4. Multiple Matching Methods

The schema supports multiple matching methods (e.g., `spike_time_overlap`, future `waveform_correlation`) by:
- Including `matching_method` in the primary key of both `UnitMatching` and `UniversalUnit`
- Different methods can produce different universal unit sets for the same sessions
- Allows comparison of results across different matching algorithms

### 5. Subject Extraction

Since `SortedSpikes` inherits from `EphysBlock` which contains `experiment_name`, the subject must be extracted by joining with `acquisition.Experiment.Subject`. The `UnitMatching.make()` function should handle this lookup when creating/updating `UniversalUnit` entries.

### 6. No Explicit Pair Tracking

The schema doesn't explicitly track which pairs of sessions were compared because:
- This information is implicit in the `UniversalUnit.UnitMatch` table: if two sessions share units in the same universal unit, they were compared
- Tracking pairs would require a complex part table with duplicate key references
- The matching execution log (`UnitMatching`) already tracks which sessions were processed

## Data Integrity Constraints

1. **Each session unit can only belong to one universal unit**: Enforced by DataJoint primary key constraints on `UniversalUnit.UnitMatch` (each `SortedSpikes.Unit` key can only appear once per universal unit)

2. **Sessions are only matched once per method**: Enforced by `UnitMatching.key_source` which excludes already-matched sessions

3. **Matching only occurs after curation**: Enforced by requiring `spike_sorting_curation.ApplyOfficialCuration` in the `key_source`

## Future Extensibility

The schema is designed to support:
- Additional matching methods (e.g., waveform correlation, combined methods)
- Different matching parameters per method
- Match confidence scores and metadata
- Manual curation/adjustment of matches

## Related Tables

- **Input**: `SortedSpikes`, `SortedSpikes.Unit` (from `spike_sorting` schema)
- **Prerequisite**: `spike_sorting_curation.ApplyOfficialCuration` (from `spike_sorting_curation` schema)
- **References**: `subject.Subject`, `ephys.Probe`, `acquisition.Experiment.Subject`



