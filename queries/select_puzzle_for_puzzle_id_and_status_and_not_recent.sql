select
p.id,
p.puzzle_id,
p.pieces,
p.rows,
p.cols,
p.piece_width,
p.mask_width,
p.table_width,
p.table_height,
p.name,
p.link,
p.description,
p.bg_color,
p.m_date,
p.owner,
p.queue,
p.status,
p.permission,
p1.puzzle_id as original_puzzle_id,
pf.url as preview_full
from Puzzle as p
JOIN PuzzleInstance as pi on (pi.instance = p.id)
join Puzzle as p1 on (p1.id = pi.original)
left outer JOIN PuzzleFile AS pf ON (pf.puzzle = p1.id and pf.name = 'preview_full') -- Get the original
where p.puzzle_id = :puzzle_id and p.status = :status
and (p.m_date is null or strftime('%s', p.m_date) <= strftime('%s', 'now', '-7 hours'));
