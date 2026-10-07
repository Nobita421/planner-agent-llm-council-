/**
 * Standard PDDL Benchmarks for AEPP Demonstrations.
 */

export const SAMPLE_PRESETS = [
  {
    id: 'blocksworld-sussman',
    name: 'Blocksworld (Sussman Anomaly)',
    description: 'Classic block stacking problem where non-interleaved subgoals fail without unstacking.',
    domain: `(define (domain blocksworld)
  (:requirements :strips :equality)
  (:predicates
    (on ?x ?y)
    (ontable ?x)
    (clear ?x)
    (handempty)
    (holding ?x)
  )

  (:action pick-up
    :parameters (?x)
    :precondition (and (clear ?x) (ontable ?x) (handempty))
    :effect (and (not (ontable ?x)) (not (clear ?x)) (not (handempty)) (holding ?x))
  )

  (:action put-down
    :parameters (?x)
    :precondition (holding ?x)
    :effect (and (not (holding ?x)) (clear ?x) (handempty) (ontable ?x))
  )

  (:action stack
    :parameters (?x ?y)
    :precondition (and (holding ?x) (clear ?y))
    :effect (and (not (holding ?x)) (not (clear ?y)) (clear ?x) (handempty) (on ?x ?y))
  )

  (:action unstack
    :parameters (?x ?y)
    :precondition (and (on ?x ?y) (clear ?x) (handempty))
    :effect (and (holding ?x) (clear ?y) (not (clear ?x)) (not (handempty)) (not (on ?x ?y)))
  )
)`,
    problem: `(define (problem bw-sussman)
  (:domain blocksworld)
  (:objects a b c)
  (:init
    (ontable a)
    (ontable b)
    (on c a)
    (clear b)
    (clear c)
    (handempty)
  )
  (:goal
    (and
      (on a b)
      (on b c)
    )
  )
)`
  },
  {
    id: 'gripper-4balls',
    name: 'Gripper (4 Balls, 2 Rooms)',
    description: 'Two-handed robot moving balls between Room A and Room B.',
    domain: `(define (domain gripper-strips)
  (:requirements :strips)
  (:predicates
    (room ?r)
    (ball ?b)
    (gripper ?g)
    (at-robby ?r)
    (at ?b ?r)
    (free ?g)
    (carry ?b ?g)
  )

  (:action move
    :parameters (?from ?to)
    :precondition (and (room ?from) (room ?to) (at-robby ?from))
    :effect (and (at-robby ?to) (not (at-robby ?from)))
  )

  (:action pick
    :parameters (?obj ?room ?gripper)
    :precondition (and (ball ?obj) (room ?room) (gripper ?gripper)
                       (at ?obj ?room) (at-robby ?room) (free ?gripper))
    :effect (and (carry ?obj ?gripper)
                 (not (at ?obj ?room))
                 (not (free ?gripper)))
  )

  (:action drop
    :parameters (?obj ?room ?gripper)
    :precondition (and (ball ?obj) (room ?room) (gripper ?gripper)
                       (carry ?obj ?gripper) (at-robby ?room))
    :effect (and (at ?obj ?room)
                 (free ?gripper)
                 (not (carry ?obj ?gripper)))
  )
)`,
    problem: `(define (problem gripper-4-balls)
  (:domain gripper-strips)
  (:objects
    rooma roomb
    ball1 ball2 ball3 ball4
    left right
  )
  (:init
    (room rooma)
    (room roomb)
    (ball ball1)
    (ball ball2)
    (ball ball3)
    (ball ball4)
    (gripper left)
    (gripper right)
    (at-robby rooma)
    (free left)
    (free right)
    (at ball1 rooma)
    (at ball2 rooma)
    (at ball3 rooma)
    (at ball4 rooma)
  )
  (:goal
    (and
      (at ball1 roomb)
      (at ball2 roomb)
      (at ball3 roomb)
      (at ball4 roomb)
    )
  )
)`
  },
  {
    id: 'logistics-simple',
    name: 'Logistics (Multi-City Package Routing)',
    description: 'Routing packages across cities using trucks and airplanes.',
    domain: `(define (domain logistics)
  (:requirements :strips)
  (:predicates
    (package ?p)
    (truck ?t)
    (airplane ?a)
    (city ?c)
    (location ?l)
    (airport ?ap)
    (at ?obj ?l)
    (in ?p ?vehicle)
    (in-city ?l ?c)
  )

  (:action load-truck
    :parameters (?p ?t ?l)
    :precondition (and (package ?p) (truck ?t) (location ?l) (at ?t ?l) (at ?p ?l))
    :effect (and (not (at ?p ?l)) (in ?p ?t))
  )

  (:action unload-truck
    :parameters (?p ?t ?l)
    :precondition (and (package ?p) (truck ?t) (location ?l) (at ?t ?l) (in ?p ?t))
    :effect (and (not (in ?p ?t)) (at ?p ?l))
  )

  (:action drive-truck
    :parameters (?t ?from ?to ?c)
    :precondition (and (truck ?t) (location ?from) (location ?to) (city ?c)
                       (at ?t ?from) (in-city ?from ?c) (in-city ?to ?c))
    :effect (and (not (at ?t ?from)) (at ?t ?to))
  )
)`,
    problem: `(define (problem log-delivery-1)
  (:domain logistics)
  (:objects
    p1 - package
    t1 - truck
    loc1 loc2 - location
    city1 - city
  )
  (:init
    (package p1)
    (truck t1)
    (location loc1)
    (location loc2)
    (city city1)
    (in-city loc1 city1)
    (in-city loc2 city1)
    (at t1 loc1)
    (at p1 loc1)
  )
  (:goal
    (at p1 loc2)
  )
)`
  },
  {
    id: 'rover-numeric',
    name: 'Rover (Action Costs & Traversal)',
    description: 'Planetary rover path navigation with total-cost and battery metrics.',
    domain: `(define (domain rover-numeric)
  (:requirements :strips :typing :action-costs)
  (:types rover waypoint)
  (:predicates
    (at ?r - rover ?w - waypoint)
    (can-traverse ?r - rover ?w1 - waypoint ?w2 - waypoint)
  )
  (:functions
    (total-cost)
  )
  (:action drive
    :parameters (?r - rover ?from - waypoint ?to - waypoint)
    :precondition (and (at ?r ?from) (can-traverse ?r ?from ?to))
    :effect (and
      (not (at ?r ?from))
      (at ?r ?to)
      (increase (total-cost) 5)
    )
  )
)`,
    problem: `(define (problem rover-p1)
  (:domain rover-numeric)
  (:objects
    r1 - rover
    w1 w2 w3 - waypoint
  )
  (:init
    (at r1 w1)
    (can-traverse r1 w1 w2)
    (can-traverse r1 w2 w3)
    (= (total-cost) 0)
  )
  (:goal
    (at r1 w3)
  )
  (:metric minimize (total-cost))
)`
  }
];
