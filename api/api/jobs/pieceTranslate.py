import os.path
import math
import time
import sys

import sqlite3
import redis
from api.app import db
from api.database import rowify, fetch_query_string
from api.tools import formatPieceMovementString, loadConfig, init_karma_key
from api.constants import COMPLETED

HOUR = 3600 # hour in seconds
TWO_HOURS = 7200
PIECE_GROUP_MOVE_MAX_BEFORE_PENALTY = 5
MAX_RECENT_POINTS = 25
MAX_KARMA = 25
MIN_KARMA = (int(MAX_KARMA/2) * -1) # -12

query_update_puzzle_m_date = """
update Puzzle set m_date = datetime('now') where id = :puzzle and (m_date < datetime('now', '-58 seconds') or m_date isnull);
"""

query_append_to_timeline = """
insert into Timeline (puzzle, player, message, points, timestamp) values
(:puzzle, :player, :message, :points, datetime('now'));
"""

query_update_user_points = """
update User set points = points + :points, score = score + :score, m_date = datetime('now') where id = :id
"""


UPDATE_BIT_ICON_EXPIRATION = """
-- Ran each time a player earns a point, but only if last_viewed has been at
-- least 1 day ago. This will potentially increase the bit expiration to the
-- next tier if the player meets the score requirements. New players that don't
-- get past the initial tier within a day will have their bit expire.

UPDATE BitIcon SET
expiration = (
  SELECT datetime('now', (
    SELECT be.extend FROM BitExpiration AS be
      JOIN User AS u
       WHERE u.score >= be.score AND u.id = :user
       ORDER BY be.score DESC LIMIT 1
    )
  )
),
last_viewed = datetime('now')
WHERE user = :user
and (last_viewed < datetime('now', '-50 minutes') or last_viewed isnull)
;
"""

query_update_puzzle_status = """update Puzzle set status = :status where id = :puzzle;"""

# Get the args from the worker and connect to the database
#try:
#    config_file = sys.argv[1]
#    config = loadConfig(config_file)
#
#    db_file = config['SQLITE_DATABASE_URI']
#    db = sqlite3.connect(db_file)
#except (IOError, IndexError):
#    # Most likely being run from a test setup
#    pass

redisConnection = redis.from_url('redis://localhost:6379/0/')

def translate(ip, user, puzzleData, piece, x, y, r, karma_change, db_file=None):
    #if db_file:
    #    db = sqlite3.connect(db_file)

    def publishMessage(topic, msg, karma_change, points=0, complete=False):
        #print(topic)
        #print(msg)
        redisConnection.publish(topic, msg)
        #time.sleep(1)

        #return (topic, msg)
        cur = db.cursor()

        #TODO: Optimize by moving last modified to redis
        # Update puzzle last modified date only if joined a piece
        if points != 0:
            cur.execute(query_update_puzzle_m_date, {'puzzle':puzzle})
        redisConnection.zadd('pcupdates', puzzle, int(time.time()))

        #TODO:
        #return (topic, msg)

        #TODO: Optimize by simply appending to a file? Maybe a puzzle instance per file
        # Append msg to timeline
        cur.execute(query_append_to_timeline, {
          'puzzle': puzzle,
          'player': user,
          'message': '', # TODO: no longer care about saving the msg
          'points': points
          })

        # Update player points
        if points != 0 and user != None:
            points_key = 'points:{user}'.format(user=user)
            pieces = int(puzzleData['pieces'])
            earns = 7
            if pieces < 200:
                earns = 0
            elif pieces < 400:
                earns = 1
            elif pieces < 800:
                earns = 2
            elif pieces < 1000:
                earns = 3
            elif pieces < 2000:
                earns = 4
            elif pieces < 3000:
                earns = 5
            elif pieces < 6000:
                earns = 6

            karma = int(redisConnection.get(karma_key))
            ## Max out recent points
            #if earns != 0:
            #    recent_points = int(redisConnection.get(points_key) or 0)
            #    if karma + 1 + recent_points + earns < MAX_KARMA:
            #        redisConnection.incr(points_key, amount=earns)
            # Doing small puzzles doesn't increase recent points, just extends points expiration.
            redisConnection.expire(points_key, TWO_HOURS)

            karma_change += 1
            # Extend the karma points expiration since it has increased
            redisConnection.expire(karma_key, HOUR)
            # Max out karma
            if karma < MAX_KARMA:
                redisConnection.incr(karma_key)
            else:
                # Max out points
                if earns != 0:
                    recent_points = int(redisConnection.get(points_key) or 0)
                    if recent_points + earns <= MAX_RECENT_POINTS:
                        redisConnection.incr(points_key, amount=earns)

            # TODO: Optimize by using redis here for user points
            db.execute(query_update_user_points, {'id':user, 'points':points, 'score':1})
            db.execute(UPDATE_BIT_ICON_EXPIRATION, {'user':user})

        # TODO: Optimize by using redis for puzzle status
        if complete:
            query = """update Puzzle set status = :completed where id = :puzzle;"""
            cur.execute(query_update_puzzle_status, {'puzzle':puzzle, 'status':COMPLETED})

        db.commit()
        cur.close()

        # return topic and msg mostly for testing
        return (topic, msg, karma_change)

    def savePiecePosition(puzzle, piece, x, y):
        # Move the piece
        redisConnection.hmset('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), {'x': x, 'y': y})
        redisConnection.zadd('pcx:{puzzle}'.format(puzzle=puzzle), piece, x)
        redisConnection.zadd('pcy:{puzzle}'.format(puzzle=puzzle), piece, y)

    def updateGroupedPiecesPositions(puzzle, piece, pieceGroup, offsetX, offsetY, newGroup=None, status=None):
        "Update all other pieces x,y in group to the offset, if newGroup then assign them to the newGroup"
        allOtherPiecesInPieceGroup = redisConnection.smembers('pcg:{puzzle}:{pieceGroup}'.format(puzzle=puzzle, pieceGroup=pieceGroup))
        allOtherPiecesInPieceGroup.remove(str(piece))
        allOtherPiecesInPieceGroup = list(allOtherPiecesInPieceGroup)
        #print 'allOtherPiecesInPieceGroup = {0}'.format(allOtherPiecesInPieceGroup)
        pipe = redisConnection.pipeline(transaction=True)
        for groupedPiece in allOtherPiecesInPieceGroup:
            pipe.hmget('pc:{puzzle}:{groupedPiece}'.format(puzzle=puzzle, groupedPiece=groupedPiece), ['x', 'y'])
        groupedPiecesXY = dict(zip(allOtherPiecesInPieceGroup, pipe.execute()))
        #print 'groupedPiecesXY'
        #print groupedPiecesXY

        pipe = redisConnection.pipeline(transaction=True)
        lines = []
        for groupedPiece in allOtherPiecesInPieceGroup:
            newX = int(groupedPiecesXY[groupedPiece][0]) + offsetX
            newY = int(groupedPiecesXY[groupedPiece][1]) + offsetY
            newPC = {'x': newX, 'y': newY}
            if newGroup != None:
                # Remove from the old group and place in newGroup
                newPC['g'] = newGroup
                pipe.sadd('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=newGroup), groupedPiece)
                pipe.srem('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=pieceGroup), groupedPiece)
            if status == '1':
                newPC['s'] = '1'
                pipe.sadd('pcfixed:{puzzle}'.format(puzzle=puzzle), groupedPiece)
                pipe.srem('pcstacked:{puzzle}'.format(puzzle=puzzle), groupedPiece)
            pipe.hmset('pc:{puzzle}:{groupedPiece}'.format(puzzle=puzzle, groupedPiece=groupedPiece), newPC)
            pipe.zadd('pcx:{puzzle}'.format(puzzle=puzzle), groupedPiece, newX)
            pipe.zadd('pcy:{puzzle}'.format(puzzle=puzzle), groupedPiece, newY)
            lines.append(formatPieceMovementString(groupedPiece, x=newX, y=newY, g=newGroup, s=status))
        if status == '1':
            pipe.sadd('pcfixed:{puzzle}'.format(puzzle=puzzle), piece)
            pipe.srem('pcstacked:{puzzle}'.format(puzzle=puzzle), piece)
            pipe.hset('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), 's', '1')
        if newGroup != None:
            # For the piece that doesn't need x,y updated remove from the old group and place in newGroup
            pipe.sadd('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=newGroup), piece)
            pipe.srem('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=pieceGroup), piece)
            pipe.hset('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), 'g', newGroup)
            lines.append(formatPieceMovementString(piece, g=newGroup))
        pipe.execute()
        return lines

    #print('translate piece {piece} for puzzle: {puzzle_id}'.format(piece=piece, puzzle_id=puzzleData['puzzle_id']))

    p = ""
    points = 0
    puzzle = puzzleData['puzzle']

    karma_key = init_karma_key(redisConnection, puzzle, ip)
    karma = int(redisConnection.get(karma_key))

    # Restrict piece to within table boundaries
    if x < 0:
        x = 0
    if x > puzzleData['table_width']:
        x = puzzleData['table_width']
    if y < 0:
        y = 0
    if y > puzzleData['table_height']:
        y = puzzleData['table_height']

    # Save the origin position
    (originX, originY) = map(int, redisConnection.hmget('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), ['x', 'y']))

    pieceGroup = redisConnection.hget('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), 'g')

    # Check proximity to other pieces with unique groups
    tolerance = int(100/2)
    #print('{0} {1} {2}'.format('pcx:{puzzle}'.format(**locals()), x - tolerance, x + tolerance))
    proximityX = set(map(int, redisConnection.zrangebyscore('pcx:{puzzle}'.format(puzzle=puzzle), x - tolerance, x + tolerance)))
    proximityY = set(map(int, redisConnection.zrangebyscore('pcy:{puzzle}'.format(puzzle=puzzle), y - tolerance, y + tolerance)))
    piecesInProximity = set.intersection(proximityX, proximityY)

    # Remove immovable pieces from the pieces in proximity
    if len(piecesInProximity) > 0:
        immovablePieces = set(map(int, redisConnection.smembers('pcfixed:{puzzle}'.format(puzzle=puzzle))))
        #print("immovablePieces {0}".format(immovablePieces))
        piecesInProximity = piecesInProximity.difference(immovablePieces)
        #print("remove immovablePieces from piecesInProximity {0}".format(piecesInProximity))

    # Remove pieces own group from the pieces in proximity
    if len(piecesInProximity) > 0:
        groupedPieces = set(map(int, redisConnection.smembers('pcg:{puzzle}:{pieceGroup}'.format(puzzle=puzzle, pieceGroup=pieceGroup))))
        piecesInProximity = piecesInProximity.difference(groupedPieces)

    piecesInProximity.add(piece)
    #print(piecesInProximity)
    lines = []
    if len(piecesInProximity) >= 4:
        pipe = redisConnection.pipeline(transaction=False)
        pipe.sadd('pcstacked:{puzzle}'.format(puzzle=puzzle), piecesInProximity)
        for pieceInProximity in piecesInProximity:
            pipe.hset('pc:{puzzle}:{pieceInProximity}'.format(puzzle=puzzle, pieceInProximity=pieceInProximity), 's', 2)
            lines.append(formatPieceMovementString(pieceInProximity, s=2))
        pipe.hmset('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), {'x': x, 'y': y, 's': 2})
        pipe.zadd('pcx:{puzzle}'.format(puzzle=puzzle), piece, x)
        pipe.zadd('pcy:{puzzle}'.format(puzzle=puzzle), piece, y)
        pipe.execute()
        p = '\n'.join(lines)
        p += '\n'

        # No further processing needed since piece is stacked
        #print p
        pieceProperties = redisConnection.hgetall('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece))

        p += formatPieceMovementString(piece, **pieceProperties)

        # If the piece is grouped move the other pieces in group
        pieceGroup = pieceProperties.get('g')
        if pieceGroup != None:
            lines = updateGroupedPiecesPositions(puzzle, piece, pieceGroup, int(pieceProperties['x']) - originX, int(pieceProperties['y']) - originY)
            p += '\n' + '\n'.join(lines)

        # Decrease karma since stacking
        if karma > MIN_KARMA:
            redisConnection.decr(karma_key)
        karma_change -= 1

        return publishMessage(u'move:{puzzle_id}'.format(puzzle_id=puzzleData['puzzle_id']), p, karma_change)

    elif len(piecesInProximity) > 1:
        #print piecesInProximity
        pipe = redisConnection.pipeline(transaction=False)
        pipe.srem('pcstacked:{puzzle}'.format(puzzle=puzzle), piecesInProximity)
        for pieceInProximity in piecesInProximity:
            pipe.hdel('pc:{puzzle}:{pieceInProximity}'.format(puzzle=puzzle, pieceInProximity=pieceInProximity), 's')
            lines.append(formatPieceMovementString(pieceInProximity, s=None))
        pipe.execute()
        p = '\n'.join(lines)
        p += '\n'

    #print 'pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece)

    # Set Piece Properties
    savePiecePosition(puzzle, piece, x, y)

    # Reset Piece Status for stacked (It's assumed that the piece being moved can't be a immovable piece)
    redisConnection.srem('pcstacked:{puzzle}'.format(puzzle=puzzle), piece)
    redisConnection.hdel('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), 's')

    # Get Piece Properties
    pieceProperties = redisConnection.hgetall('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece))
    #print(pieceProperties)
    p += formatPieceMovementString(piece, **pieceProperties)

    # Get Adjacent Piece Properties
    adjacentPiecesList = map(int, filter(lambda x: x not in ('x', 'y', 'r', 'w', 'h', 'b', 'rotate', 'g', 's'), pieceProperties.keys()))
    pipe = redisConnection.pipeline(transaction=False)
    for adjacentPiece in adjacentPiecesList:
        pipe.hgetall('pc:{puzzle}:{adjacentPiece}'.format(puzzle=puzzle, adjacentPiece=adjacentPiece))
    adjacentPieceProperties = dict(zip(adjacentPiecesList, pipe.execute()))
    #print adjacentPieceProperties

    # Check if piece is close enough to any adjacent piece
    pieceGroup = pieceProperties.get('g', None)
    #print 'pieceGroup = {0} {1}'.format(pieceGroup, isinstance(pieceGroup, str))
    hasProcessedPieceGroupMovement = False
    for adjacentPiece in adjacentPiecesList:
        # Skip if adjacent piece in same group
        if pieceGroup:
            if redisConnection.sismember('pcg:{puzzle}:{pieceGroup}'.format(puzzle=puzzle, pieceGroup=pieceGroup), adjacentPiece):
                #print('Skipping since adjacent piece in same group')
                continue

        (offsetFromPieceX, offsetFromPieceY) = map(int, pieceProperties.get(str(adjacentPiece)).split(','))
        targetX = offsetFromPieceX + int(pieceProperties['x'])
        targetY = offsetFromPieceY + int(pieceProperties['y'])
        adjacentPieceProps = adjacentPieceProperties.get(adjacentPiece)

        xlow = targetX - tolerance
        xhigh = targetX + tolerance
        #print('check proximity for x {x} > {xlow} and {x} < {xhigh}'.format(x=adjacentPieceProps['x'], xlow=xlow, xhigh=xhigh))

        # Skip If the adjacent piece is not within range of the targetX and targetY
        if not ((int(adjacentPieceProps['x']) > (targetX - tolerance)) and (int(adjacentPieceProps['x']) < (targetX + tolerance))):
            #print('{adjacentPiece} not within x range'.format(adjacentPiece=adjacentPiece))
            continue

        ylow = targetY - tolerance
        yhigh = targetY + tolerance
        #print('check proximity for y {y} > {ylow} and {y} < {yhigh}'.format(y=adjacentPieceProps['y'], ylow=ylow, yhigh=yhigh))
        if not ((int(adjacentPieceProps['y']) > (targetY - tolerance)) and (int(adjacentPieceProps['y']) < (targetY + tolerance))):
            #print('{adjacentPiece} not within y range'.format(adjacentPiece=adjacentPiece))
            continue

        #print('{adjacentPiece} within range {x}, {y}'.format(adjacentPiece=adjacentPiece, x=adjacentPieceProps['x'], y=adjacentPieceProps['y']))

        # The piece can be joined to the adjacent piece
        points = 4
        pieceProperties['x'] = int(adjacentPieceProps['x']) - offsetFromPieceX
        pieceProperties['y'] = int(adjacentPieceProps['y']) - offsetFromPieceY

        # Set immovable status if adjacent piece is immovable (Will save and update other grouped pieces later)
        if adjacentPieceProps.get('s') == '1':
            pieceProperties['s'] = '1'

        savePiecePosition(puzzle, piece, x=pieceProperties['x'], y=pieceProperties['y'])

        # Update Piece group
        countOfPiecesInPieceGroup = redisConnection.scard('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=pieceProperties.get('g', piece)))
        adjacentPieceGroup = adjacentPieceProps.get('g', adjacentPiece)
        if countOfPiecesInPieceGroup == 0:
            # Update Piece group to that of the adjacent piece since it may already be in a group
            #print('add {piece} to adjacent pieces group {g}'.format(piece=piece, g=adjacentPieceGroup))
            redisConnection.sadd('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=adjacentPieceGroup), piece, adjacentPiece)
            redisConnection.hset('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), 'g', adjacentPieceGroup)
            redisConnection.hset('pc:{puzzle}:{adjacentPiece}'.format(puzzle=puzzle, adjacentPiece=adjacentPiece), 'g', adjacentPieceGroup)

            # Save the piece immovable status
            if pieceProperties.get('s') == '1':
                redisConnection.hset('pc:{puzzle}:{piece}'.format(puzzle=puzzle, piece=piece), 's', '1')
                redisConnection.sadd('pcfixed:{puzzle}'.format(puzzle=puzzle), piece)

            pieceProperties['g'] = adjacentPieceGroup
            p += '\n' + formatPieceMovementString(piece, **pieceProperties)
            p += '\n' + formatPieceMovementString(adjacentPiece, g=adjacentPieceGroup)

        else:
            # Decide which group should be merged into the other
            #print('decide group for {piece}'.format(piece=piece))
            countOfPiecesInAdjacentPieceGroup = redisConnection.scard('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=adjacentPieceGroup))
            #print('adjacentPieceGroup count: {0}'.format(countOfPiecesInAdjacentPieceGroup))
            #print('pieceGroup count: {0}'.format(countOfPiecesInPieceGroup))
            if adjacentPieceProps.get('s') == '1':
                # The adjacent piece is immovable so update all pieces that are joining to also be immovable
                #print('updating pieces in group to be in adjacent piece group and setting them to be immovable')
                lines = updateGroupedPiecesPositions(puzzle, piece, pieceGroup, int(pieceProperties['x']) - originX, int(pieceProperties['y']) - originY, newGroup=adjacentPieceGroup, status='1')
                pieceProperties['g'] = adjacentPieceGroup
            elif countOfPiecesInPieceGroup <= countOfPiecesInAdjacentPieceGroup:
                #print('updating pieces in group to be in adjacent piece group')
                lines = updateGroupedPiecesPositions(puzzle, piece, pieceGroup, int(pieceProperties['x']) - originX, int(pieceProperties['y']) - originY, newGroup=adjacentPieceGroup)
                pieceProperties['g'] = adjacentPieceGroup

            elif countOfPiecesInAdjacentPieceGroup == 0:
                # The adjacent piece is not in a group
                #print('adjacent piece not in group')
                lines = [formatPieceMovementString(adjacentPiece, g=pieceProperties['g'])]

                # Update positions except the piece since its group is not changing either
                lines.extend(updateGroupedPiecesPositions(puzzle, piece, pieceGroup, int(pieceProperties['x']) - originX, int(pieceProperties['y']) - originY))

                pipe = redisConnection.pipeline(transaction=True)
                pipe.sadd('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=pieceProperties['g']), adjacentPiece)
                pipe.hset('pc:{puzzle}:{adjacentPiece}'.format(puzzle=puzzle, adjacentPiece=adjacentPiece), 'g', pieceProperties['g'])
                pipe.execute()
            else:
                # Adjacent group is smaller so update just the group in adjacent pieces
                #print('updating adjacent piece group to be in moved piece group')
                lines = []

                # Update the positions of the moved group first
                lines.extend(updateGroupedPiecesPositions(puzzle, piece, pieceGroup, int(pieceProperties['x']) - originX, int(pieceProperties['y']) - originY))

                # Add the adjacent pieces to the group
                # TODO: unless the adjacent piece is immovable
                piecesInAdjacentPieceGroup = redisConnection.smembers('pcg:{puzzle}:{adjacentPieceGroup}'.format(puzzle=puzzle, adjacentPieceGroup=adjacentPieceGroup))
                pipe = redisConnection.pipeline(transaction=True)
                for groupedAdjacentPiece in piecesInAdjacentPieceGroup:
                    pipe.sadd('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=pieceProperties['g']), groupedAdjacentPiece)
                    pipe.srem('pcg:{puzzle}:{g}'.format(puzzle=puzzle, g=adjacentPieceGroup), groupedAdjacentPiece)
                    pipe.hset('pc:{puzzle}:{groupedAdjacentPiece}'.format(puzzle=puzzle, groupedAdjacentPiece=groupedAdjacentPiece), 'g', pieceProperties['g'])
                    lines.append(formatPieceMovementString(groupedAdjacentPiece, g=pieceProperties['g']))
                pipe.execute()

            #print lines
            p += '\n' + '\n'.join(lines)
            p += '\n' + formatPieceMovementString(piece, **pieceProperties)
            hasProcessedPieceGroupMovement = True

        # No need to check other adjacent pieces
        break

    # Update other piece positions that are in the group if they haven't already been moved from the group merge
    if pieceGroup != None and not hasProcessedPieceGroupMovement:
        # Decrement karma since moving a piece that is in a group
        pieceGroupCount = redisConnection.scard('pcg:{puzzle}:{pieceGroup}'.format(puzzle=puzzle, pieceGroup=pieceGroup))
        if pieceGroupCount > PIECE_GROUP_MOVE_MAX_BEFORE_PENALTY:
            # print 'decr karma since moving piec in group'
            if karma > MIN_KARMA:
                redisConnection.decr(karma_key)
            karma_change -= 1

        lines = updateGroupedPiecesPositions(puzzle, piece, pieceGroup, int(pieceProperties['x']) - originX, int(pieceProperties['y']) - originY)
        p += '\n' + '\n'.join(lines)

    # Check if the puzzle is complete
    complete = False
    if pieceProperties.get('s') == '1':
        immovableGroupCount = redisConnection.scard('pcfixed:{puzzle}'.format(puzzle=puzzle))
        if int(immovableGroupCount) == int(puzzleData.get('pieces')):
            #print("Puzzle is complete: {0} == {1}".format(immovableGroupCount, puzzleData.get('pieces')))
            complete = True

    return publishMessage(u'move:{puzzle_id}'.format(puzzle_id=puzzleData['puzzle_id']), p, karma_change, points=points, complete=complete)
