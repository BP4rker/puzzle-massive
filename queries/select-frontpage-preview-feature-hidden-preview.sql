select pzf.name
from Puzzle as p
join PuzzleFeatureData as pfd on (pfd.puzzle = p.id)
join PuzzleFeature as pzf on (pzf.id = pfd.puzzle_feature)
where p.puzzle_id = :puzzle_id
and pzf.enabled = 1
AND pzf.slug = 'hidden-preview'
;
