class TrackableObject:
    def __init__(self, objectID, centroid):
        self.objectID = objectID
        self.centroids = [centroid]
        self.first_x = centroid[0]  # Store first X position
        self.last_x = centroid[0]   # Initialize last X position
        self.counted = False

    def update(self, centroid):
        self.centroids.append(centroid)
        self.last_x = centroid[0]  # Update last X position
