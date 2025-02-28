class TrackableObject:
    def __init__(self, objectID, centroid):
        self.objectID = objectID
        self.centroids = [centroid]
        self.first_y = centroid[1]  # Store first Y position
        self.last_y = centroid[1]  # Initialize last Y position
        self.counted = False

    def update(self, centroid):
        self.centroids.append(centroid)
        self.last_y = centroid[1]  # Update last Y position