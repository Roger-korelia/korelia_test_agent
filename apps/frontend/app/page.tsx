import React from "react";
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="max-w-md mx-auto p-6">
        <div className="bg-white rounded-lg shadow-lg p-8 text-center">
          <h1 className="text-3xl font-bold text-gray-800 mb-4">Electronics Design Agent</h1>
          <p className="text-gray-600 mb-6">
            Test the electronics design agent system
          </p>
          <Link 
            href="/chat" 
            className="inline-block bg-blue-600 text-white px-8 py-3 rounded-lg hover:bg-blue-700 transition-colors"
          >
            Start Chat
          </Link>
        </div>
      </div>
    </main>
  );
}
