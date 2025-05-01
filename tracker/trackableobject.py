
import random

class TrackableObject:
    def __init__(self, objectID, centroid):
        self.objectID = objectID
        self.centroids = [centroid]
        self.first_y = centroid[1]
        self.last_y = centroid[1]
        self.first_x = centroid[0]
        self.last_x = centroid[0]
        self.counted = False
        self.nickname = self.generate_nickname()

    def update(self, centroid):
        self.centroids.append(centroid)
        self.last_y = centroid[1]
        self.last_x = centroid[0]

    def generate_nickname(self):
        nicknames = [
            "Rocket", "Ninja", "Flash", "Shadow", "Blaze", "Pixie", "Storm",
            "Bolt", "Drift", "Phantom", "Maverick", "Comet", "Vortex",
            "Ghost", "Falcon", "Wolfie", "Dragon", "Tiger", "Eagle"
        ]
        return random.choice(nicknames) + str(random.randint(1, 99))
