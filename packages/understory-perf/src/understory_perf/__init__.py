"""Load and latency harness for the Understory detection pipeline.

Answers one question with numbers rather than adjectives: how many AOIs can this
pipeline monitor on a given machine without falling permanently behind NISAR's
12-day repeat cycle — and where does it break when pushed past that.

Nothing in the science packages imports this; it drives them from above.
"""

__version__ = "0.1.0"
